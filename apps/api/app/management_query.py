"""
Management Query Engine (Section 62).

Drafts professional-sounding query text from an exception's already-real
fields (module, reason, amount, root cause) — no invented facts, purely
templating what the exception record already contains. The user reviews and
edits before sending (Section 62's own requirement), same principle as
every other "AI drafts, human approves" module in this system.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class QueryDraft:
    subject: str
    query_text: str
    required_information: str
    due_date: date


def draft_client_query(
    module: str, reason: str, amount: float | None, root_cause: str, days_to_respond: int = 7
) -> QueryDraft:
    subject = f"{module} — Query re. {reason[:80]}" if len(reason) > 80 else f"{module} — Query re. {reason}"

    amount_text = f" (amount: ₹{amount:,.2f})" if amount else ""

    body = (
        f"During our review of {module}, we identified the following item requiring clarification{amount_text}:\n\n"
        f"{reason}\n\n"
        f"Based on the information available to us, this may relate to: {root_cause.replace('_', ' ').title()}.\n\n"
        f"Could you please provide an explanation for this item, along with any supporting documentation "
        f"(e.g. bank confirmation, challan copy, invoice, or ledger extract) that would help us close this out?"
    )

    required_info = {
        "MISSING_TRANSACTION": "Proof of payment (bank confirmation or challan acknowledgment) for the amount in question.",
        "DATA_ENTRY_ERROR": "The original source document (challan/invoice) to confirm the correct amount.",
        "STATUTORY_ERROR": "Confirmation of subsequent payment (if any) and the basis for the shortfall.",
        "DUPLICATE": "Confirmation of which record (if either) is genuine, and evidence of any correction made.",
        "TIMING_DIFFERENCE": "Confirmation that payment/collection is genuinely still pending, and expected timing.",
        "UNKNOWN": "Any documentation or explanation that clarifies the nature of this item.",
    }.get(root_cause, "Supporting documentation for this item.")

    return QueryDraft(
        subject=subject, query_text=body, required_information=required_info,
        due_date=date.today() + timedelta(days=days_to_respond),
    )
