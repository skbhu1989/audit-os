from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, require_roles, CurrentUser
from ..caro import draft_statutory_dues_clause, draft_fraud_clause, draft_repayment_of_borrowings_clause
from ..ai_assistant import build_duplicate_vendor_answer
from ..loans import check_loan

router = APIRouter(prefix="/engagements/{engagement_id}/caro", tags=["caro"])
WRITE_ROLES = ("FIRM_ADMIN", "PARTNER", "MANAGER", "SENIOR")
REVIEW_ROLES = ("FIRM_ADMIN", "PARTNER", "MANAGER", "EQCR_REVIEWER")
APPROVE_ROLES = ("FIRM_ADMIN", "PARTNER")


class InitResult(BaseModel):
    clauses_seeded: int
    clauses_already_existed: int
    data_backed_drafts: int


@router.post("/init", response_model=InitResult)
async def init_caro(engagement_id: UUID, user: CurrentUser = Depends(require_roles(*WRITE_ROLES))):
    """Seeds a caro_assessment row per clause (idempotent), then auto-drafts
    the two clauses this system has real data for. Every other clause is
    seeded with its default applicability and left INSUFFICIENT_DATA —
    never silently marked 'no exceptions.'"""
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select performance_materiality, reporting_date from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        clauses = await conn.fetch("select clause_no, default_applicability from caro_clause")
        seeded, existed = 0, 0
        for c in clauses:
            existing = await conn.fetchrow(
                "select id from caro_assessment where engagement_id=$1 and clause_no=$2", engagement_id, c["clause_no"]
            )
            if existing:
                existed += 1
                continue
            applicability = "APPLICABLE" if c["default_applicability"] == "LIKELY_APPLICABLE" else "REQUIRES_ASSESSMENT"
            await conn.execute(
                """insert into caro_assessment (engagement_id, clause_no, applicability, data_status, status)
                   values ($1,$2,$3,'INSUFFICIENT_DATA','NOT_STARTED')""",
                engagement_id, c["clause_no"], applicability,
            )
            seeded += 1

        # Clause vii: Statutory Dues
        gst = [dict(r) for r in await conn.fetch(
            """select e.risk_level, e.reason from reconciliation_exception e join reconciliation_run r on r.id=e.run_id
               where r.engagement_id=$1 and r.recon_type like 'GST_%'""", engagement_id)]
        tds = [dict(r) for r in await conn.fetch(
            """select e.risk_level, e.reason from reconciliation_exception e join reconciliation_run r on r.id=e.run_id
               where r.engagement_id=$1 and r.recon_type='TDS_RECONCILIATION'""", engagement_id)]
        payroll = [dict(r) for r in await conn.fetch(
            """select e.risk_level, e.reason from reconciliation_exception e join reconciliation_run r on r.id=e.run_id
               where r.engagement_id=$1 and r.recon_type like 'PAYROLL_%'""", engagement_id)]
        dues_draft = draft_statutory_dues_clause(gst, tds, payroll)
        await conn.execute(
            "update caro_assessment set data_status=$1, draft_response=$2, status='DRAFT', updated_at=now() where engagement_id=$3 and clause_no='vii'",
            dues_draft.data_status, dues_draft.draft_response, engagement_id,
        )

        # Clause xi: Fraud
        je_counts = await conn.fetchrow(
            "select count(*) filter (where risk_level in ('HIGH','CRITICAL')) as hc, count(*) as total "
            "from journal where engagement_id=$1 and risk_level is not null", engagement_id,
        )
        vendors = await conn.fetch("select id, name from vendor where engagement_id=$1", engagement_id)
        dup_answer = build_duplicate_vendor_answer([dict(v) for v in vendors])
        dup_pairs = dup_answer.data_used.count(" vs ") if dup_answer else 0
        fraud_draft = draft_fraud_clause(je_counts["hc"] or 0, je_counts["total"] or 0, dup_pairs)
        await conn.execute(
            "update caro_assessment set data_status=$1, draft_response=$2, status=$3, updated_at=now() where engagement_id=$4 and clause_no='xi'",
            fraud_draft.data_status, fraud_draft.draft_response,
            "DRAFT" if fraud_draft.data_status == "DATA_BACKED" else "NOT_STARTED", engagement_id,
        )
        if fraud_draft.data_status == "INSUFFICIENT_DATA":
            await conn.execute(
                "update caro_assessment set data_gap_reason=$1 where engagement_id=$2 and clause_no='xi'",
                fraud_draft.data_gap_reason, engagement_id,
            )

        # Clause ix: Repayment of Borrowings — first made data-backed here,
        # now that the Loans module (this phase) provides real loan data.
        loan_rows = await conn.fetch(
            "select lender_or_borrower, direction, outstanding_balance, maturity_date from loan where engagement_id=$1",
            engagement_id,
        )
        borrowings = [dict(r) for r in loan_rows if r["direction"] == "BORROWING"]
        overdue = []
        for l in borrowings:
            check = check_loan(
                {"lender_or_borrower": l["lender_or_borrower"], "direction": l["direction"],
                 "outstanding_balance": float(l["outstanding_balance"]), "maturity_date": l["maturity_date"]},
                eng["reporting_date"],
            )
            if check.flag:
                overdue.append({"lender_or_borrower": l["lender_or_borrower"], "days_overdue": check.days_overdue,
                                 "outstanding_balance": float(l["outstanding_balance"])})
        repayment_draft = draft_repayment_of_borrowings_clause(overdue, len(borrowings))
        await conn.execute(
            "update caro_assessment set data_status=$1, draft_response=$2, status=$3, data_gap_reason=$4, updated_at=now() where engagement_id=$5 and clause_no='ix'",
            repayment_draft.data_status, repayment_draft.draft_response,
            "DRAFT" if repayment_draft.data_status == "DATA_BACKED" else "NOT_STARTED",
            repayment_draft.data_gap_reason, engagement_id,
        )

        data_backed = await conn.fetchval(
            "select count(*) from caro_assessment where engagement_id=$1 and data_status='DATA_BACKED'", engagement_id
        )

    return InitResult(clauses_seeded=seeded, clauses_already_existed=existed, data_backed_drafts=data_backed)


class CaroAssessmentOut(BaseModel):
    clause_no: str
    title: str
    topic_summary: str
    applicability: str
    data_status: str
    draft_response: str | None
    data_gap_reason: str | None
    final_response: str | None
    status: str
    preparer_id: UUID | None
    reviewer_id: UUID | None
    approver_id: UUID | None


@router.get("", response_model=list[CaroAssessmentOut])
async def list_caro(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        rows = await conn.fetch(
            """select c.clause_no, cl.title, cl.topic_summary, c.applicability, c.data_status,
                      c.draft_response, c.data_gap_reason, c.final_response, c.status,
                      c.preparer_id, c.reviewer_id, c.approver_id
               from caro_assessment c join caro_clause cl on cl.clause_no = c.clause_no
               where c.engagement_id=$1
               order by array_position(array['i','ii','iii','iv','v','vi','vii','viii','ix','x',
                 'xi','xii','xiii','xiv','xv','xvi','xvii','xviii','xix','xx','xxi'], c.clause_no)""",
            engagement_id,
        )
    # An engagement with no CARO assessment yet is not an error condition —
    # it's the normal state before /caro/init has been called. Returning a
    # 404 here (the original Phase 12 design) forced every caller, including
    # the frontend, to treat "not yet initialized" as an error to catch and
    # swallow — caught by a real browser test seeing this show up as a
    # genuine console error on every fresh engagement's CARO page, even
    # though the UI itself degraded gracefully. An empty list is the more
    # correct REST response for "the collection exists, nothing is in it yet."
    return [CaroAssessmentOut(**dict(r)) for r in rows]


async def _get_assessment(conn, engagement_id, clause_no):
    row = await conn.fetchrow(
        "select id, status, preparer_id from caro_assessment where engagement_id=$1 and clause_no=$2",
        engagement_id, clause_no,
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clause assessment not found")
    return row


@router.post("/{clause_no}/prepare", status_code=204)
async def prepare_clause(engagement_id: UUID, clause_no: str, user: CurrentUser = Depends(require_roles(*WRITE_ROLES))):
    async with tenant_conn(user.firm_id) as conn:
        a = await _get_assessment(conn, engagement_id, clause_no)
        if a["status"] not in ("NOT_STARTED", "DRAFT"):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot prepare from status {a['status']}")
        await conn.execute(
            "update caro_assessment set status='PREPARED', preparer_id=$1, prepared_at=now() where id=$2",
            user.user_id, a["id"],
        )


@router.post("/{clause_no}/review", status_code=204)
async def review_clause(engagement_id: UUID, clause_no: str, user: CurrentUser = Depends(require_roles(*REVIEW_ROLES))):
    async with tenant_conn(user.firm_id) as conn:
        a = await _get_assessment(conn, engagement_id, clause_no)
        if a["status"] != "PREPARED":
            raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot review from status {a['status']} (must be PREPARED)")
        if a["preparer_id"] and str(a["preparer_id"]) == user.user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Segregation of duties: the preparer cannot also review (SA 220)")
        await conn.execute(
            "update caro_assessment set status='REVIEWED', reviewer_id=$1, reviewed_at=now() where id=$2",
            user.user_id, a["id"],
        )


class ApproveClauseRequest(BaseModel):
    final_response: str


@router.post("/{clause_no}/approve", status_code=204)
async def approve_clause(
    engagement_id: UUID, clause_no: str, body: ApproveClauseRequest,
    user: CurrentUser = Depends(require_roles(*APPROVE_ROLES)),
):
    """final_response is required (not optional like the working-paper
    approve endpoint) — CARO clause language is the actual audit report
    text, and per Section I, the system must never auto-issue it. A partner
    must explicitly type or confirm the final wording."""
    async with tenant_conn(user.firm_id) as conn:
        a = await _get_assessment(conn, engagement_id, clause_no)
        if a["status"] != "REVIEWED":
            raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot approve from status {a['status']} (must be REVIEWED)")
        if a["preparer_id"] and str(a["preparer_id"]) == user.user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Segregation of duties: the preparer cannot also approve (SA 220)")
        await conn.execute(
            "update caro_assessment set status='APPROVED', approver_id=$1, approved_at=now(), final_response=$2 where id=$3",
            user.user_id, body.final_response, a["id"],
        )
