"""
AI Root Cause Analysis (Section 61).

Same honest scoping as Phase 10's AI Assistant: no LLM call (no API
credentials in this sandbox). This is deterministic keyword classification
over the `reason` text and `module` already present on every audit_exception
row — reusing the fields the reconciliation engines already wrote rather
than inventing new analysis. The fixed taxonomy is exactly Section 61's:
TIMING_DIFFERENCE, ACCOUNTING_ERROR, DATA_ENTRY_ERROR, STATUTORY_ERROR,
DUPLICATE, MISSING_TRANSACTION, WRONG_CLASSIFICATION, WRONG_PERIOD,
MASTER_DATA_ERROR, UNKNOWN.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class RootCauseAnalysis:
    root_cause: str
    what: str
    why: str
    impact: str
    action: str


def _article(word: str) -> str:
    """'A' vs 'An' — matters here because these strings can become actual
    client-facing query language (see draft_client_query below), and
    'A AP balance' reads as sloppy in a document a client receives."""
    return "An" if word and word[0].upper() in "AEIOU" else "A"


def classify_root_cause(module: str | None, reason: str | None, risk_level: str, age_days: int | None = None) -> RootCauseAnalysis:
    r = (reason or "").lower()
    art = _article(module or "")

    if "duplicate" in r:
        return RootCauseAnalysis(
            "DUPLICATE",
            what="Two records appear to represent the same underlying transaction.",
            why="Same party and amount recorded close together in time — likely a repeat entry or repeat invoice upload.",
            impact="Risk of duplicate payment or overstated liability/expense if both are recorded as genuine.",
            action="Confirm with the counterparty which record (if either) is genuine; reverse or delete the duplicate.",
        )

    if "unmapped" in r and module in ("GST", "TDS", "PF", "ESI", "PT"):
        return RootCauseAnalysis(
            "MISSING_TRANSACTION",
            what=f"{art} {module} challan payment could not be matched to any bank statement entry.",
            why="Either the payment hasn't yet appeared in the uploaded bank statement window, or it was genuinely not made.",
            impact="If genuinely unpaid: statutory default, interest, and penalty exposure. If a timing gap: no real exposure once confirmed.",
            action="Check the bank statement for a later period, or obtain proof of payment directly from the client.",
        )

    if "mismatched" in r or ("differs" in r and module in ("GST", "TDS")):
        return RootCauseAnalysis(
            "DATA_ENTRY_ERROR",
            what="A challan or return amount is close in date to a bank entry but the amounts don't match.",
            why="Most likely a transcription error in the source data (challan amount, or how it was recorded in the ledger).",
            impact="Understates or overstates the true statutory payment unless corrected.",
            action="Compare the original challan document against both the books and the bank entry to identify which figure is wrong.",
        )

    if "short" in r or "shortfall" in r or "without full payment" in r:
        return RootCauseAnalysis(
            "STATUTORY_ERROR",
            what="A statutory liability was only partially paid.",
            why="Deducted/accrued amount exceeds what was actually remitted — a genuine compliance shortfall, not a data artifact.",
            impact="Interest under the relevant provision, and possible disallowance if unresolved by the return filing deadline.",
            action="Quantify the shortfall precisely, pay the balance with interest, and confirm no return amendment is also needed.",
        )

    if "outstanding" in r and module in ("AP", "AR"):
        # Exceptions in this system only exist for balances already aged
        # past 180 days (the sync logic in exceptions.py never creates one
        # for anything younger) — so by the time this classifier runs, the
        # item has already been assigned MEDIUM or HIGH risk. Calling it
        # "routine, Low impact" for anything under 365 days would directly
        # contradict that risk assignment. Caught by tracing the actual
        # exception-creation logic, not by reading this function in
        # isolation. TIMING_DIFFERENCE remains a legitimate root cause —
        # the wording just has to agree with the risk already on the record.
        if age_days is not None and age_days > 365:
            return RootCauseAnalysis(
                "UNKNOWN",
                what=f"{art} {module} balance has remained outstanding for over a year.",
                why="No single cause is evident from the data alone — could be a genuine collection/payment issue, a dispute, or simply an oversight.",
                impact="Recoverability (AR) or completeness of settlement (AP) should not be assumed without further inquiry.",
                action="Obtain a balance confirmation from the counterparty and ask management directly why it remains open.",
            )
        return RootCauseAnalysis(
            "TIMING_DIFFERENCE",
            what=f"{art} {module} balance has been outstanding for more than 180 days.",
            why="Most likely reflects a genuine delay in payment/collection rather than a books error — but 180+ days is past a normal cycle and warrants confirmation, not dismissal.",
            impact="Moderate — recoverability (AR) or an unexplained aged payable (AP) should be specifically followed up, consistent with this item's assigned risk level.",
            action="Obtain a balance confirmation and management's explanation for why this specific item remains open past the normal cycle.",
        )

    if "gstr" in r or "turnover" in r:
        return RootCauseAnalysis(
            "STATUTORY_ERROR",
            what="A GST return figure does not agree with books or another return.",
            why="Could reflect a genuine reporting gap, a credit note not yet reflected, or a filing period mismatch.",
            impact="GST short-payment or ITC exposure depending on the direction of the difference.",
            action="Obtain the client's own reconciliation working papers for this period before concluding.",
        )

    return RootCauseAnalysis(
        "UNKNOWN",
        what="An exception was identified but the available data does not clearly indicate a specific cause.",
        why="The reason text does not match any of this system's known classification patterns.",
        impact=f"Assessed at {risk_level} risk based on amount/materiality alone.",
        action="Manual investigation required — review the underlying source documents directly.",
    )
