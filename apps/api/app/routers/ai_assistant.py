from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, CurrentUser
from ..ai_assistant import (
    detect_intent, parse_indian_amount, build_duplicate_vendor_answer,
    build_journal_risk_answer, build_gst_reconciliation_answer,
    build_tds_reconciliation_answer, build_trial_balance_answer, build_no_data_answer,
    AIAnswer,
)

router = APIRouter(prefix="/engagements/{engagement_id}/ai-assistant", tags=["ai-assistant"])


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    question: str
    intent: str | None
    answer: str
    data_used: str
    calculation: str
    source: str
    standard: str
    evidence: str
    implication: str
    procedure: str


NOT_YET_BUILT = {
    "large_payments": "identifying 'new' vendors requires a vendor-onboarding-date field this schema does not yet capture — only payment amount can be checked, not vendor novelty",
    "working_papers": None,  # actually handled below with real data
}


@router.post("/ask", response_model=AskResponse)
async def ask(engagement_id: UUID, body: AskRequest, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id = $1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        intent = detect_intent(body.question)
        result: AIAnswer | None = None

        if intent == "duplicate_vendor":
            vendors = await conn.fetch("select id, name from vendor where engagement_id = $1", engagement_id)
            result = build_duplicate_vendor_answer([dict(v) for v in vendors])
            if result is None:
                result = build_no_data_answer("No vendor pairs in this engagement's vendor master meet the similarity threshold for a possible duplicate.")

        elif intent in ("journal_year_end", "journal_risk"):
            eng_row = await conn.fetchrow("select reporting_date from engagement where id = $1", engagement_id)
            if intent == "journal_year_end":
                rows = await conn.fetch(
                    """select id, posted_date, posted_by as user, amount, risk_level as level, risk_reasons as reasons
                       from journal where engagement_id = $1
                       and posted_date between $2::date - interval '4 days' and $2::date
                       order by posted_date""",
                    engagement_id, eng_row["reporting_date"],
                )
                filter_desc = f"posted within the final days before the reporting date ({eng_row['reporting_date']})"
            else:
                rows = await conn.fetch(
                    """select id, posted_date, posted_by as user, amount, risk_level as level, risk_reasons as reasons
                       from journal where engagement_id = $1 and risk_level in ('HIGH','CRITICAL')
                       order by risk_score desc""",
                    engagement_id,
                )
                filter_desc = "scored HIGH or CRITICAL risk"
            journals = [
                {"id": str(r["id"])[:8], "date": str(r["posted_date"]), "user": r["user"],
                 "amount": float(r["amount"]), "level": r["level"], "reasons": r["reasons"]}
                for r in rows
            ]
            result = build_journal_risk_answer(journals, filter_desc)
            if result is None:
                result = build_no_data_answer(f"No journal entries in this engagement {filter_desc}.")

        elif intent == "gst_reconciliation":
            rows = await conn.fetch(
                """select r.recon_type, e.document_no, e.period, e.difference, e.risk_level
                   from reconciliation_exception e join reconciliation_run r on r.id = e.run_id
                   where r.engagement_id = $1 and r.recon_type like 'GST_%'""",
                engagement_id,
            )
            result = build_gst_reconciliation_answer([dict(r) for r in rows])
            if result is None:
                result = build_no_data_answer(
                    "No GST reconciliation has been run for this engagement yet, or it found no exceptions. "
                    "Run POST .../analytics/gst-reconciliation/run first."
                )

        elif intent == "tds_reconciliation":
            rows = await conn.fetch(
                """select e.document_no as section, e.reason
                   from reconciliation_exception e join reconciliation_run r on r.id = e.run_id
                   where r.engagement_id = $1 and r.recon_type = 'TDS_RECONCILIATION'""",
                engagement_id,
            )
            result = build_tds_reconciliation_answer([dict(r) for r in rows])
            if result is None:
                result = build_no_data_answer(
                    "No TDS reconciliation has been run for this engagement yet, or it found no exceptions. "
                    "Run POST .../analytics/tds-reconciliation/run first."
                )

        elif intent == "trial_balance":
            tb_totals = await conn.fetchrow(
                """select coalesce(sum(t.debit),0) as total_debit, coalesce(sum(t.credit),0) as total_credit
                   from (select distinct on (account_id) account_id, debit, credit from trial_balance_line
                         where engagement_id = $1 order by account_id, as_of_date desc, created_at desc) t""",
                engagement_id,
            )
            unmapped = await conn.fetchval(
                "select count(*) from account where engagement_id = $1 and mapped_by is null", engagement_id
            )
            ties = abs(float(tb_totals["total_debit"]) - float(tb_totals["total_credit"])) < 1.0
            result = build_trial_balance_answer(ties, float(tb_totals["total_debit"]), float(tb_totals["total_credit"]), unmapped)

        elif intent == "large_payments":
            threshold = parse_indian_amount(body.question)
            if threshold is None:
                result = build_no_data_answer("Could not determine the amount threshold from the question — try phrasing like 'payments above 25 lakh'.")
            else:
                rows = await conn.fetch(
                    """select txn_date, description, amount from bank_transaction
                       where engagement_id = $1 and amount < 0 and abs(amount) >= $2
                       order by amount""",
                    engagement_id, threshold,
                )
                if rows:
                    listing = "; ".join(f"{r['txn_date']}: {r['description']} (₹{abs(r['amount']):,.0f})" for r in rows)
                    result = AIAnswer(
                        answer=f"{len(rows)} bank payment(s) above ₹{threshold:,.0f} found.",
                        data_used=listing,
                        calculation=f"Bank transactions with amount < 0 (money out) and absolute value >= {threshold:,.0f}.",
                        source="DATA_QUERY",
                        standard="SA 500 (audit evidence)",
                        evidence="Bank statement extract for this engagement.",
                        implication="Large payments warrant vendor/purpose verification, particularly for related parties or new counterparties (vendor-novelty check not available — see procedure).",
                        procedure="Vouch each payment to supporting invoice/contract. " + (NOT_YET_BUILT["large_payments"] or ""),
                    )
                else:
                    result = build_no_data_answer(f"No bank payments above ₹{threshold:,.0f} found in this engagement's uploaded bank statement.")

        if result is None:
            result = build_no_data_answer(
                "This question does not match a supported analysis type yet. Supported: duplicate vendors, "
                "journal entries at year-end or by risk level, GST reconciliation, TDS reconciliation, "
                "trial balance status, and large payments."
            )

    return AskResponse(question=body.question, intent=intent, **result.__dict__)
