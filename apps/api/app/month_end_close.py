"""
Month-End Close (Section 59).

Same honesty principle as everywhere else: `is_system_computed=True` tasks
get their status derived live from real reconciliation data; the rest
default to NOT_STARTED and require a human to update them, because no
engine in this system computes their state yet (fixed assets, inventory,
intercompany, related parties, FX, deferred tax, leases — none of these
have ingestion or reconciliation built).
"""
from __future__ import annotations
from dataclasses import dataclass

# (category, task_name, is_system_computed)
DEFAULT_CLOSE_TASKS = [
    ("Bank", "Bank reconciliation prepared and reviewed", True),
    ("GST", "GST reconciliation (Books/GSTR-1/GSTR-3B/GSTR-2B) completed", True),
    ("TDS", "TDS reconciliation (ledger/challan/return) completed", True),
    ("Payroll", "PF/ESI/PT statutory reconciliation completed", True),
    ("AP", "AP ageing reviewed, duplicate invoices checked", True),
    ("AR", "AR ageing reviewed", True),
    ("Fixed Assets", "Fixed asset additions/disposals reviewed, depreciation recalculated", False),
    ("Inventory", "Inventory reconciled to books, valuation reviewed", False),
    ("Accruals", "Accrual completeness reviewed", False),
    ("Prepayments", "Prepayment schedule reviewed", False),
    ("Revenue Cut-off", "Revenue cut-off tested at period end", False),
    ("Expense Cut-off", "Expense cut-off tested at period end", False),
    ("Loans", "Loan balances and interest reconciled to lender statements", False),
    ("Intercompany", "Intercompany balances confirmed and eliminated", False),
    ("Related Parties", "Related party transactions identified and disclosed", False),
    ("FX", "Foreign currency balances revalued", False),
    ("Provisions", "Provisions reviewed for adequacy", False),
    ("Deferred Tax", "Deferred tax asset/liability recomputed", False),
    ("Leases", "Lease ROU asset and liability schedules updated", False),
]


@dataclass
class SystemStatusResult:
    status: str  # 'COMPLETE' | 'REVIEW_REQUIRED' | 'NOT_STARTED'
    evidence_note: str


def derive_bank_status(recon_items: list[dict]) -> SystemStatusResult:
    if not recon_items:
        return SystemStatusResult("NOT_STARTED", "No bank statement or GL bank ledger data available yet.")
    unmatched = sum(1 for r in recon_items if r["status"] != "MATCHED")
    if unmatched == 0:
        return SystemStatusResult("COMPLETE", f"All {len(recon_items)} items matched.")
    return SystemStatusResult("REVIEW_REQUIRED", f"{unmatched} of {len(recon_items)} items unmatched — see Bank Reconciliation.")


def derive_recon_status(exceptions: list[dict], has_run: bool) -> SystemStatusResult:
    if not has_run:
        return SystemStatusResult("NOT_STARTED", "Reconciliation has not been run yet for this period.")
    if not exceptions:
        return SystemStatusResult("COMPLETE", "No exceptions identified.")
    material = sum(1 for e in exceptions if e.get("risk_level") in ("HIGH", "CRITICAL"))
    return SystemStatusResult("REVIEW_REQUIRED", f"{len(exceptions)} exception(s), {material} material.")


def derive_ap_ar_status(ageing_items: list[dict], duplicate_count: int = 0) -> SystemStatusResult:
    old_items = sum(1 for a in ageing_items if a["bucket"] in (">365", "181-365"))
    if not ageing_items and duplicate_count == 0:
        return SystemStatusResult("COMPLETE", "No outstanding balances or duplicate invoices identified.")
    parts = []
    if old_items:
        parts.append(f"{old_items} balance(s) outstanding over 180 days")
    if duplicate_count:
        parts.append(f"{duplicate_count} possible duplicate invoice(s)")
    if not parts:
        return SystemStatusResult("COMPLETE", f"{len(ageing_items)} outstanding balance(s), all under 180 days.")
    return SystemStatusResult("REVIEW_REQUIRED", "; ".join(parts))
