"""
Loans & Borrowings Audit (Section 31), feeding directly into:
- Going Concern (Section 84: "debt maturity, defaults")
- CARO clause (ix): Repayment of Borrowings — this is the first loan data
  this system has ever had, so it's also wired into caro.py to make that
  clause DATA_BACKED instead of the INSUFFICIENT_DATA it's shown since
  Phase 12.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date


@dataclass
class LoanFlag:
    lender_or_borrower: str
    direction: str
    outstanding_balance: float
    flag: str | None
    days_overdue: int | None


def check_loan(loan: dict, as_of: date) -> LoanFlag:
    """loan: {'lender_or_borrower','direction','outstanding_balance',
    'maturity_date','interest_rate','principal_amount'}."""
    maturity = loan.get("maturity_date")
    outstanding = loan["outstanding_balance"]

    if loan["direction"] == "BORROWING" and maturity and outstanding > 0 and maturity < as_of:
        days_overdue = (as_of - maturity).days
        return LoanFlag(
            loan["lender_or_borrower"], loan["direction"], outstanding,
            f"Loan matured {days_overdue} day(s) ago with an outstanding balance of {outstanding:,.0f} — "
            f"possible repayment default (relevant to CARO clause ix and going concern assessment)",
            days_overdue,
        )
    return LoanFlag(loan["lender_or_borrower"], loan["direction"], outstanding, None, None)


@dataclass
class InterestConsistencyFlag:
    lender_or_borrower: str
    expected_annual_interest: float | None
    flag: str | None


def check_interest_consistency(loan: dict, actual_finance_cost_total: float | None) -> InterestConsistencyFlag:
    """A simple materiality-scale sanity check: does this loan's own expected
    annual interest (principal x rate) look plausible against the total
    Finance Costs recorded in the GL? This can't attribute finance cost to
    a specific loan (the GL doesn't break it out that way) — it only flags
    when a single loan's expected interest alone would exceed total
    recorded finance costs, which is a real red flag regardless."""
    rate = loan.get("interest_rate")
    if rate is None or loan["direction"] != "BORROWING":
        return InterestConsistencyFlag(loan["lender_or_borrower"], None, None)

    expected = loan["outstanding_balance"] * (rate / 100)
    if actual_finance_cost_total is not None and expected > actual_finance_cost_total:
        return InterestConsistencyFlag(
            loan["lender_or_borrower"], round(expected, 2),
            f"This single loan's expected annual interest ({expected:,.0f}) exceeds the engagement's "
            f"total recorded Finance Costs ({actual_finance_cost_total:,.0f}) — interest may be unrecorded "
            f"or capitalized rather than expensed",
        )
    return InterestConsistencyFlag(loan["lender_or_borrower"], round(expected, 2), None)


@dataclass
class LoanGlReconciliation:
    loans_total: float
    gl_total: float
    difference: float
    status: str


def reconcile_loans_to_gl(borrowing_total: float, gl_borrowings_balance: float | None) -> LoanGlReconciliation:
    if gl_borrowings_balance is None:
        return LoanGlReconciliation(borrowing_total, 0.0, borrowing_total, "NO_DATA")
    diff = round(borrowing_total - gl_borrowings_balance, 2)
    status = "MATCHED" if abs(diff) < 1.0 else "MISMATCH"
    return LoanGlReconciliation(borrowing_total, gl_borrowings_balance, diff, status)
