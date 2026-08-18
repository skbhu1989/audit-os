"""
Fixed Asset Intelligence (Section 23): "Rs X repairs-related expenditure —
review capitalisation" pattern from the spec's own example.

Scoped honestly: this can only flag journal entries booked to an expense
account whose NAME suggests repairs/maintenance (keyword match on the
ledger name) with an amount above a materiality-scale threshold — it
cannot inspect invoice line-item descriptions (no OCR/document intelligence
exists in this system) to determine whether the expenditure is genuinely
routine repair or actually an asset enhancement. The finding is explicitly
framed as "review capitalisation," never "this is capital expenditure."
"""
from __future__ import annotations
from dataclasses import dataclass

REPAIR_KEYWORDS = ("repair", "maintenance", "renovation", "refurbish")


@dataclass
class CapitalizationFlag:
    fact: str
    source_data: str
    rule: str
    analysis: str
    conclusion: str
    confidence: str
    recommended_action: str
    journal_id: str
    amount: float


def flag_potential_capital_expenditure(
    journal_entries: list[dict], materiality_threshold: float | None
) -> list[CapitalizationFlag]:
    """journal_entries: [{'id','account_name','amount','narration'}] —
    already filtered by the caller to expense-classified accounts only."""
    flags = []
    # Without a materiality figure, fall back to a fixed absolute threshold
    # (Rs 1 lakh) rather than flagging every small repair expense — a fixed
    # fallback, not a fabricated materiality calculation.
    threshold = materiality_threshold * 0.10 if materiality_threshold else 100000.0

    for je in journal_entries:
        account_lower = je["account_name"].lower()
        if not any(kw in account_lower for kw in REPAIR_KEYWORDS):
            continue
        if je["amount"] < threshold:
            continue

        flags.append(CapitalizationFlag(
            fact=f"Rs {je['amount']:,.0f} booked to '{je['account_name']}' (narration: {je.get('narration') or 'none'}).",
            source_data=f"Journal entry {je['id']}.",
            rule="Expenditure that enhances an asset's capacity, extends its useful life, or improves its "
                 "performance beyond original condition should generally be capitalized rather than expensed "
                 "as routine repair (Ind AS 16 / AS 10 recognition principle).",
            analysis=(
                f"This entry is booked to an account whose name suggests routine repair/maintenance, but the "
                f"amount (Rs {je['amount']:,.0f}) is large enough relative to "
                f"{'performance materiality' if materiality_threshold else 'a general absolute threshold, since no materiality figure was available'} "
                f"to warrant checking whether the underlying expenditure is genuinely routine or actually an "
                f"asset enhancement. This system cannot read the underlying invoice description — only the "
                f"ledger classification and amount."
            ),
            conclusion="POTENTIAL MISCLASSIFICATION BETWEEN REPAIRS EXPENSE AND CAPITAL EXPENDITURE — REVIEW CAPITALISATION.",
            confidence="MEDIUM",
            recommended_action="Obtain the underlying invoice/work order and assess against the capitalization criteria; "
                                "if capital in nature, reclassify to the appropriate fixed asset category and begin depreciation.",
            journal_id=je["id"], amount=je["amount"],
        ))
    return flags
