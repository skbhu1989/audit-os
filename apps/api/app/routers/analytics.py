from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, require_roles, CurrentUser
from ..analytics import suggest_fs_mapping, tb_balance_flag, score_journal

router = APIRouter(prefix="/engagements/{engagement_id}", tags=["analytics"])
WRITE_ROLES = ("FIRM_ADMIN", "PARTNER", "MANAGER", "SENIOR")


# ---------- Trial Balance mapping ----------

class MappingSuggestionOut(BaseModel):
    account_id: UUID
    ledger_name: str
    current_fs_line: str | None
    suggested_fs_statement: str
    suggested_fs_line: str | None
    suggested_note_ref: str | None
    confidence: float
    matched_keyword: str | None
    is_suspense: bool
    already_mapped: bool  # mapped_by is set -> a human has already approved something


@router.get("/trial-balance/mapping-suggestions", response_model=list[MappingSuggestionOut])
async def get_mapping_suggestions(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    """Read-only preview — does not write anything. Suggestions are computed
    on the fly from the current ledger names so this always reflects the
    latest FS_MAPPING_RULES without needing a separate 'run' step first."""
    async with tenant_conn(user.firm_id) as conn:
        accounts = await conn.fetch(
            "select id, ledger_name, fs_line, mapped_by from account where engagement_id = $1", engagement_id
        )
    out = []
    for a in accounts:
        s = suggest_fs_mapping(a["ledger_name"])
        out.append(MappingSuggestionOut(
            account_id=a["id"], ledger_name=a["ledger_name"], current_fs_line=a["fs_line"],
            suggested_fs_statement=s.fs_statement, suggested_fs_line=s.fs_line,
            suggested_note_ref=s.note_ref, confidence=s.confidence, matched_keyword=s.matched_keyword,
            is_suspense=s.is_suspense, already_mapped=a["mapped_by"] is not None,
        ))
    return out


class ApplySuggestionsRequest(BaseModel):
    min_confidence: float = 0.7


class ApplySuggestionsResult(BaseModel):
    accounts_updated: int


@router.post("/trial-balance/mapping-suggestions/apply", response_model=ApplySuggestionsResult)
async def apply_high_confidence_suggestions(
    engagement_id: UUID, body: ApplySuggestionsRequest,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    """Writes fs_statement/fs_line for suggestions at or above min_confidence,
    but deliberately does NOT set mapped_by/mapped_at — that field is the
    'a human approved this' signal (Section O: 'require human approval for
    final mapping'), and auto-applying a suggestion is not the same as an
    auditor approving it. A reviewer still has to hit the approve endpoint
    below for each line (or an explicit bulk-approve, which this is not)."""
    async with tenant_conn(user.firm_id) as conn:
        accounts = await conn.fetch(
            "select id, ledger_name from account where engagement_id = $1 and mapped_by is null", engagement_id
        )
        updated = 0
        for a in accounts:
            s = suggest_fs_mapping(a["ledger_name"])
            if s.confidence >= body.min_confidence:
                await conn.execute(
                    """update account set fs_statement = $1, fs_line = $2, note_ref = $3, is_suspense = $4
                       where id = $5""",
                    s.fs_statement, s.fs_line, s.note_ref, s.is_suspense, a["id"],
                )
                updated += 1
    return ApplySuggestionsResult(accounts_updated=updated)


class ApproveMappingRequest(BaseModel):
    fs_statement: str
    fs_line: str | None = None
    note_ref: str | None = None
    is_suspense: bool = False


@router.patch("/accounts/{account_id}/mapping", status_code=204)
async def approve_mapping(
    engagement_id: UUID, account_id: UUID, body: ApproveMappingRequest,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    """The actual human-approval step — sets mapped_by/mapped_at."""
    async with tenant_conn(user.firm_id) as conn:
        row = await conn.fetchrow(
            "select 1 from account where id = $1 and engagement_id = $2", account_id, engagement_id
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
        await conn.execute(
            """update account set fs_statement = $1, fs_line = $2, note_ref = $3, is_suspense = $4,
                      mapped_by = $5, mapped_at = now()
               where id = $6""",
            body.fs_statement, body.fs_line, body.note_ref, body.is_suspense, user.user_id, account_id,
        )


# ---------- TB balance-direction flags ----------

class TbFlagRunResult(BaseModel):
    lines_checked: int
    lines_flagged: int


@router.post("/analytics/tb-flags/run", response_model=TbFlagRunResult)
async def run_tb_flags(engagement_id: UUID, user: CurrentUser = Depends(require_roles(*WRITE_ROLES))):
    async with tenant_conn(user.firm_id) as conn:
        # latest TB line per account
        rows = await conn.fetch(
            """select distinct on (a.id) t.id as tb_line_id, a.fs_line, t.debit, t.credit
               from trial_balance_line t join account a on a.id = t.account_id
               where t.engagement_id = $1
               order by a.id, t.as_of_date desc, t.created_at desc""",
            engagement_id,
        )
        flagged = 0
        for r in rows:
            flag = tb_balance_flag(r["fs_line"], float(r["debit"]), float(r["credit"]))
            await conn.execute("update trial_balance_line set flag = $1 where id = $2", flag, r["tb_line_id"])
            if flag:
                flagged += 1
    return TbFlagRunResult(lines_checked=len(rows), lines_flagged=flagged)


# ---------- Journal risk scoring ----------

class JournalRiskRunResult(BaseModel):
    journals_scored: int
    risk_distribution: dict[str, int]


@router.post("/analytics/journal-risk/run", response_model=JournalRiskRunResult)
async def run_journal_risk(engagement_id: UUID, user: CurrentUser = Depends(require_roles(*WRITE_ROLES))):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow(
            "select reporting_date, performance_materiality from engagement where id = $1", engagement_id
        )
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        journals = await conn.fetch(
            "select id, posted_date, posted_by, narration, amount from journal where engagement_id = $1",
            engagement_id,
        )
        distribution = {"LOW": 0, "MODERATE": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        for j in journals:
            lines = await conn.fetch(
                """select jl.debit, jl.credit, a.ledger_name from journal_line jl
                   join account a on a.id = jl.account_id where jl.journal_id = $1""",
                j["id"],
            )
            dr_name = next((l["ledger_name"] for l in lines if l["debit"] and l["debit"] > 0), "")
            cr_name = next((l["ledger_name"] for l in lines if l["credit"] and l["credit"] > 0), "")

            result = score_journal(
                j["posted_date"], j["posted_by"], j["narration"], float(j["amount"]),
                dr_name, cr_name, eng["reporting_date"],
                float(eng["performance_materiality"]) if eng["performance_materiality"] else None,
            )
            await conn.execute(
                "update journal set risk_score = $1, risk_level = $2, risk_reasons = $3 where id = $4",
                result.score, result.level, result.reasons, j["id"],
            )
            distribution[result.level] += 1

    return JournalRiskRunResult(journals_scored=len(journals), risk_distribution=distribution)


# ---------- Dashboard ----------

class FlaggedJournalOut(BaseModel):
    id: UUID
    posted_date: str
    posted_by: str | None
    narration: str | None
    amount: float
    risk_score: float | None
    risk_level: str | None
    risk_reasons: list[str] | None


class TbFlagOut(BaseModel):
    ledger_name: str
    fs_line: str | None
    debit: float
    credit: float
    flag: str


class AnalyticsDashboard(BaseModel):
    tb_ties: bool
    total_debit: float
    total_credit: float
    unmapped_account_count: int
    risk_distribution: dict[str, int]
    top_flagged_journals: list[FlaggedJournalOut]
    tb_flags: list[TbFlagOut]


@router.get("/analytics/dashboard", response_model=AnalyticsDashboard)
async def get_dashboard(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        tb_totals = await conn.fetchrow(
            """select coalesce(sum(t.debit),0) as total_debit, coalesce(sum(t.credit),0) as total_credit
               from (
                 select distinct on (account_id) account_id, debit, credit
                 from trial_balance_line where engagement_id = $1
                 order by account_id, as_of_date desc, created_at desc
               ) t""",
            engagement_id,
        )
        unmapped = await conn.fetchval(
            "select count(*) from account where engagement_id = $1 and mapped_by is null", engagement_id
        )
        risk_rows = await conn.fetch(
            "select risk_level, count(*) from journal where engagement_id = $1 and risk_level is not null group by risk_level",
            engagement_id,
        )
        distribution = {"LOW": 0, "MODERATE": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        for r in risk_rows:
            distribution[r["risk_level"]] = r["count"]

        top_journals = await conn.fetch(
            """select id, posted_date, posted_by, narration, amount, risk_score, risk_level, risk_reasons
               from journal where engagement_id = $1 and risk_score is not null
               order by risk_score desc limit 10""",
            engagement_id,
        )

        tb_flag_rows = await conn.fetch(
            """select distinct on (a.id) a.ledger_name, a.fs_line, t.debit, t.credit, t.flag
               from trial_balance_line t join account a on a.id = t.account_id
               where t.engagement_id = $1 and t.flag is not null
               order by a.id, t.as_of_date desc, t.created_at desc""",
            engagement_id,
        )

    return AnalyticsDashboard(
        tb_ties=abs(float(tb_totals["total_debit"]) - float(tb_totals["total_credit"])) < 1.0,
        total_debit=float(tb_totals["total_debit"]), total_credit=float(tb_totals["total_credit"]),
        unmapped_account_count=unmapped,
        risk_distribution=distribution,
        top_flagged_journals=[
            FlaggedJournalOut(
                id=j["id"], posted_date=j["posted_date"].isoformat(), posted_by=j["posted_by"],
                narration=j["narration"], amount=float(j["amount"]), risk_score=float(j["risk_score"]) if j["risk_score"] is not None else None,
                risk_level=j["risk_level"], risk_reasons=j["risk_reasons"],
            ) for j in top_journals
        ],
        tb_flags=[
            TbFlagOut(ledger_name=r["ledger_name"], fs_line=r["fs_line"], debit=float(r["debit"]), credit=float(r["credit"]), flag=r["flag"])
            for r in tb_flag_rows
        ],
    )
