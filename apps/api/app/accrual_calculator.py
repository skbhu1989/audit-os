"""
Accrual Gap Calculator (Section 21).

Honestly scoped: the spec's own example ("Annual audit fee = Rs 12 lakh...
if only Rs 8 lakh booked") uses a KNOWN reference figure — it's not derived
from trend analysis. This system has no multi-year GL history to auto-derive
an "expected annual amount" (Meridian Fashions has a handful of journal
entries spanning a few months, not 12 months of consistent data), so
building a true time-series anomaly detector would produce results this
system can't actually validate against real data. What's built instead is
exactly what the spec's example demonstrates: the accountant/auditor
supplies the known expected annual figure, and the system computes the gap
against actual booked-to-date, structured per Section 51's format.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class AccrualGapResult:
    fact: str
    source_data: str
    rule: str
    analysis: str
    conclusion: str
    confidence: str
    recommended_action: str
    potential_accrual: float


def compute_accrual_gap(
    ledger_name: str, expected_annual_amount: float, booked_to_date: float, months_elapsed: int
) -> AccrualGapResult | None:
    if months_elapsed <= 0 or months_elapsed > 12:
        raise ValueError("months_elapsed must be between 1 and 12")

    pro_rata_expected = expected_annual_amount * (months_elapsed / 12)
    gap = round(pro_rata_expected - booked_to_date, 2)

    if gap <= 0:
        return None  # booked amount already meets or exceeds the pro-rata expectation — no gap to flag

    confidence = "HIGH" if gap > expected_annual_amount * 0.10 else "MEDIUM"

    return AccrualGapResult(
        fact=f"'{ledger_name}': Rs {booked_to_date:,.0f} booked against a pro-rated expectation of "
             f"Rs {pro_rata_expected:,.0f} ({months_elapsed} of 12 months, full-year expected Rs {expected_annual_amount:,.0f}).",
        source_data=f"User-provided expected annual amount for '{ledger_name}', compared against booked-to-date from the ledger.",
        rule="An expense expected to recur evenly across the year should show roughly proportional booking to "
             "date; a shortfall against the pro-rata expectation may indicate an unrecorded liability requiring accrual.",
        analysis=(
            f"Rs {gap:,.0f} less has been booked than the pro-rata expectation for this period. This could mean "
            f"the expense is genuinely lower this year, the pattern isn't actually even across months (e.g. "
            f"seasonal), or — the reason this check exists — the year-end invoice/accrual simply hasn't been "
            f"recorded yet."
        ),
        conclusion=f"POTENTIAL UNRECORDED ACCRUAL OF APPROXIMATELY Rs {gap:,.0f} REQUIRING FURTHER INVESTIGATION.",
        confidence=confidence,
        recommended_action="Confirm with the vendor/service provider whether an invoice for this period is outstanding; "
                            "if so, accrue the estimated amount before finalizing the books.",
        potential_accrual=gap,
    )
