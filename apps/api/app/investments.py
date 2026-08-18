"""
Investments Audit (Section 32).
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date

STALE_VALUATION_DAYS = 120  # a fair value more than ~4 months old is stale for a reporting-date balance


@dataclass
class InvestmentFlag:
    investee_name: str
    cost: float
    fair_value: float | None
    unrealized_gain_loss: float | None
    flags: list[str]


def assess_investment(inv: dict, reporting_date: date) -> InvestmentFlag:
    """inv: {'investee_name','cost','fair_value','fair_value_date','classification'}."""
    flags = []
    fv = inv.get("fair_value")
    fv_date = inv.get("fair_value_date")
    gain_loss = None

    if fv is None:
        flags.append("No fair value on record — cannot assess valuation as at the reporting date")
    else:
        gain_loss = round(fv - inv["cost"], 2)
        if fv_date and (reporting_date - fv_date).days > STALE_VALUATION_DAYS:
            flags.append(
                f"Fair value is dated {(reporting_date - fv_date).days} days before the reporting date — "
                f"valuation may not reflect current conditions"
            )
        if gain_loss < 0 and abs(gain_loss) > inv["cost"] * 0.20:
            flags.append(
                f"Fair value is {abs(gain_loss)/inv['cost']*100:.0f}% below cost — consider whether this "
                f"indicates impairment requiring specific assessment (Ind AS 109), not just a routine mark-to-market move"
            )

    return InvestmentFlag(inv["investee_name"], inv["cost"], fv, gain_loss, flags)


@dataclass
class InvestmentGlReconciliation:
    investments_total: float
    gl_total: float
    difference: float
    status: str


def reconcile_investments_to_gl(cost_total: float, gl_investments_balance: float | None) -> InvestmentGlReconciliation:
    if gl_investments_balance is None:
        return InvestmentGlReconciliation(cost_total, 0.0, cost_total, "NO_DATA")
    diff = round(cost_total - gl_investments_balance, 2)
    status = "MATCHED" if abs(diff) < 1.0 else "MISMATCH"
    return InvestmentGlReconciliation(cost_total, gl_investments_balance, diff, status)
