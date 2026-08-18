from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, CurrentUser
from ..master_data_intelligence import find_same_identifier_different_name
from ..fixed_asset_intelligence import flag_potential_capital_expenditure
from ..accrual_calculator import compute_accrual_gap

router = APIRouter(prefix="/engagements/{engagement_id}", tags=["finance-intelligence"])


# ---------- Daily Finance Briefing (Section 39) ----------

class BriefingOut(BaseModel):
    critical_issues: int
    reconciliation_issues: int
    documents_pending: int
    receivables_due: float
    statutory_payments_approaching: list[dict]
    revenue_trend: str  # honest "INSUFFICIENT_DATA" when only one period exists
    margin_trend: str
    recommended_actions: list[str]


@router.get("/finance-briefing", response_model=BriefingOut)
async def get_finance_briefing(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    """Reuses every engine already built — Exceptions, Data Centre, AR,
    Compliance Calendar — rather than recomputing anything. Revenue and
    margin trend are honestly reported as INSUFFICIENT_DATA: this system
    only has one trial balance snapshot per engagement (no period-over-
    period comparison data), so a real trend figure would be fabricated,
    not computed."""
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        critical = await conn.fetchval(
            "select count(*) from audit_exception where engagement_id=$1 and risk_level in ('HIGH','CRITICAL') and status not in ('CLOSED','WAIVED')",
            engagement_id,
        ) or 0
        total_open = await conn.fetchval(
            "select count(*) from audit_exception where engagement_id=$1 and status not in ('CLOSED','WAIVED')",
            engagement_id,
        ) or 0
        reconciliation_issues = max(0, total_open - critical)

        required_missing = await conn.fetchval(
            "select count(*) from data_coverage where engagement_id=$1 and status='NOT_UPLOADED'", engagement_id
        ) or 0

        ar_total = await conn.fetchval(
            """select coalesce(sum(i.total_value),0) from invoice i
               where i.engagement_id=$1 and i.direction='SALES'""",
            engagement_id,
        ) or 0

        upcoming = await conn.fetch(
            """select statutory_type, filing_or_payment, period, due_date, amount
               from compliance_calendar_item
               where engagement_id=$1 and actual_date is null and due_date between current_date and current_date + interval '15 days'
               order by due_date""",
            engagement_id,
        )

        top_exceptions = await conn.fetch(
            """select reason, amount, difference from audit_exception
               where engagement_id=$1 and risk_level in ('HIGH','CRITICAL') and status not in ('CLOSED','WAIVED')
               order by risk_level, updated_at desc limit 3""",
            engagement_id,
        )

    actions = []
    for e in top_exceptions:
        amt = e["amount"] if e["amount"] is not None else e["difference"]
        actions.append(f"Resolve: {e['reason']}" + (f" (Rs {float(amt):,.0f})" if amt else ""))
    if upcoming:
        nearest = upcoming[0]
        actions.append(f"Statutory due soon: {nearest['filing_or_payment']} ({nearest['statutory_type']}) due {nearest['due_date']}")
    if required_missing > 0 and not actions:
        actions.append(f"{required_missing} required dataset(s) not yet uploaded — visit Data Centre")
    if not actions:
        actions.append("No urgent items identified from current data.")

    return BriefingOut(
        critical_issues=critical, reconciliation_issues=reconciliation_issues,
        documents_pending=required_missing, receivables_due=float(ar_total),
        statutory_payments_approaching=[
            {"type": r["statutory_type"], "filing_or_payment": r["filing_or_payment"], "period": r["period"],
             "due_date": str(r["due_date"]), "amount": float(r["amount"]) if r["amount"] else None}
            for r in upcoming
        ],
        revenue_trend="INSUFFICIENT_DATA — only one trial balance period is available; period-over-period comparison requires multiple periods.",
        margin_trend="INSUFFICIENT_DATA — same reason as revenue_trend.",
        recommended_actions=actions[:3],
    )


# ---------- Vendor/Customer Master Data Intelligence (Section 27-28) ----------

class MasterDataFindingOut(BaseModel):
    fact: str
    rule: str
    analysis: str
    conclusion: str
    confidence: str
    recommended_action: str
    party_ids: list[str]


@router.get("/finance-intelligence/master-data", response_model=list[MasterDataFindingOut])
async def get_master_data_intelligence(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")
        vendors = await conn.fetch("select id, name, pan, gstin, bank_account_masked from vendor where engagement_id=$1", engagement_id)
        customers = await conn.fetch("select id, name, pan, gstin from customer where engagement_id=$1", engagement_id)

    findings = find_same_identifier_different_name(
        [{"id": r["id"], "name": r["name"], "pan": r["pan"], "gstin": r["gstin"], "bank_account_masked": r["bank_account_masked"]} for r in vendors],
        "vendor",
    ) + find_same_identifier_different_name(
        [{"id": r["id"], "name": r["name"], "pan": r["pan"], "gstin": r["gstin"], "bank_account_masked": None} for r in customers],
        "customer",
    )
    return [MasterDataFindingOut(**f.__dict__) for f in findings]


# ---------- Fixed Asset Intelligence: repairs-vs-capital (Section 23) ----------

class CapitalizationFlagOut(BaseModel):
    fact: str
    rule: str
    analysis: str
    conclusion: str
    confidence: str
    recommended_action: str
    journal_id: str
    amount: float


@router.get("/finance-intelligence/capitalization-review", response_model=list[CapitalizationFlagOut])
async def get_capitalization_review(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select performance_materiality from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")
        rows = await conn.fetch(
            """select j.id, a.ledger_name, j.amount, j.narration
               from journal_line jl join journal j on j.id = jl.journal_id join account a on a.id = jl.account_id
               where j.engagement_id=$1 and jl.debit > 0""",
            engagement_id,
        )

    entries = [{"id": str(r["id"]), "account_name": r["ledger_name"], "amount": float(r["amount"]), "narration": r["narration"]} for r in rows]
    materiality = float(eng["performance_materiality"]) if eng["performance_materiality"] else None
    flags = flag_potential_capital_expenditure(entries, materiality)
    return [CapitalizationFlagOut(**f.__dict__) for f in flags]


# ---------- Accrual Gap Calculator (Section 21) ----------

class AccrualGapRequest(BaseModel):
    ledger_name: str
    expected_annual_amount: float
    months_elapsed: int


class AccrualGapOut(BaseModel):
    fact: str | None
    rule: str | None
    analysis: str | None
    conclusion: str | None
    confidence: str | None
    recommended_action: str | None
    potential_accrual: float | None
    no_gap: bool


@router.post("/finance-intelligence/accrual-gap", response_model=AccrualGapOut)
async def calculate_accrual_gap(engagement_id: UUID, body: AccrualGapRequest, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")
        # Trial balance is the authoritative period-end position — check it
        # first. journal_line only captures transaction-level detail and
        # can legitimately be empty for a ledger whose balance came from
        # opening balances or entries never re-uploaded as journal detail
        # (exactly Meridian Fashions' real Finance Costs: Rs 78,00,000 sits
        # in the trial balance but zero of it exists as journal_line rows).
        # Caught by testing against real data, not by reading the query.
        booked = await conn.fetchval(
            """select sum(t.debit - t.credit) from trial_balance_line t join account a on a.id=t.account_id
               where t.engagement_id=$1 and lower(a.ledger_name) = lower($2)""",
            engagement_id, body.ledger_name,
        )
        if booked is None:
            booked = await conn.fetchval(
                """select coalesce(sum(jl.debit - jl.credit), 0)
                   from journal_line jl join journal j on j.id=jl.journal_id join account a on a.id=jl.account_id
                   where j.engagement_id=$1 and lower(a.ledger_name) = lower($2)""",
                engagement_id, body.ledger_name,
            )

    try:
        result = compute_accrual_gap(body.ledger_name, body.expected_annual_amount, float(booked or 0), body.months_elapsed)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    if result is None:
        return AccrualGapOut(fact=None, rule=None, analysis=None, conclusion=None, confidence=None, recommended_action=None, potential_accrual=None, no_gap=True)
    return AccrualGapOut(**result.__dict__, no_gap=False)
