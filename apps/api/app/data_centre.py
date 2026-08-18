"""
Pre-Audit Module: the Data Centre (Section 17) and Dynamic Checklist
(Section 18).

The core distinction this module exists to enforce (Section 39):
DATA GAP ("nothing uploaded yet") is not the same thing as a
RECONCILIATION EXCEPTION ("uploaded, but doesn't tie"). Every other
module in this system computes exceptions; this module is the one place
that tracks the *absence* of data as a first-class, non-alarming status.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class ChecklistItem:
    dataset_type: str
    label: str
    requirement: str  # 'REQUIRED' | 'RECOMMENDED' | 'OPTIONAL'
    reason: str


def build_checklist(profile: dict) -> list[ChecklistItem]:
    """profile keys: has_gst (bool), has_employees (bool), has_inventory (bool),
    has_fixed_assets (bool)."""
    items = [
        ChecklistItem("TRIAL_BALANCE", "Trial Balance", "REQUIRED", "Always required — the foundation of every other analysis."),
        ChecklistItem("GENERAL_LEDGER", "General Ledger / Journal Register", "REQUIRED", "Always required for journal entry testing and GL analytics."),
        ChecklistItem("VENDOR_MASTER", "Vendor Master", "REQUIRED", "Needed for AP reconciliation and duplicate vendor detection."),
        ChecklistItem("CUSTOMER_MASTER", "Customer Master", "REQUIRED", "Needed for AR reconciliation and ageing."),
        ChecklistItem("SALES_REGISTER", "Sales Register", "REQUIRED", "Needed for revenue and GST completeness testing."),
        ChecklistItem("PURCHASE_REGISTER", "Purchase Register", "REQUIRED", "Needed for AP and ITC testing."),
        ChecklistItem("BANK_STATEMENT", "Bank Statement", "REQUIRED", "Always required for bank reconciliation."),
    ]

    if profile.get("has_gst", True):
        items += [
            ChecklistItem("GSTR1", "GSTR-1", "REQUIRED", "GST registration detected — needed for outward-supply reconciliation."),
            ChecklistItem("GSTR3B", "GSTR-3B", "REQUIRED", "GST registration detected — needed for period-total reconciliation."),
            ChecklistItem("GSTR2B", "GSTR-2B", "RECOMMENDED", "Needed for ITC reconciliation; recommended rather than required since ITC risk is assessable without it, just less precisely."),
        ]
    else:
        items.append(ChecklistItem("GSTR1", "GSTR-1 / GSTR-3B / GSTR-2B", "OPTIONAL", "No GST registration on this entity's profile — GST reconciliation is not applicable."))

    items += [
        ChecklistItem("TDS_LEDGER", "TDS Ledger", "REQUIRED", "Always required — nearly every entity has some TDS obligation."),
        ChecklistItem("TDS_CHALLAN", "TDS Challans", "REQUIRED", "Needed to confirm TDS was actually paid, not just deducted."),
        ChecklistItem("TDS_RETURN", "TDS Return (24Q/26Q/27Q)", "RECOMMENDED", "Needed for deductee-level reconciliation; recommended since section-level reconciliation is possible without it."),
    ]

    if profile.get("has_employees", True):
        items += [
            ChecklistItem("EMPLOYEE_MASTER", "Employee Master", "REQUIRED", "Employees detected on this entity's profile."),
            ChecklistItem("PAYROLL_REGISTER", "Payroll Register", "REQUIRED", "Needed for PF/ESI/PT reconciliation."),
            ChecklistItem("PF_CHALLAN", "PF Challans", "REQUIRED", "Needed to confirm PF was actually deposited."),
        ]
    else:
        items.append(ChecklistItem("PAYROLL_REGISTER", "Payroll Register", "OPTIONAL", "No employees on this entity's profile — payroll statutory reconciliation is not applicable."))

    if profile.get("has_fixed_assets", True):
        items.append(ChecklistItem("FIXED_ASSET_REGISTER", "Fixed Asset Register", "REQUIRED", "Fixed assets detected on the trial balance — required for FAR reconciliation and depreciation testing."))

    if profile.get("has_inventory", True):
        items.append(ChecklistItem("INVENTORY_REGISTER", "Inventory Register", "REQUIRED", "Inventory detected on the trial balance — required for inventory valuation and ageing testing."))

    items += [
        ChecklistItem("LOAN_REGISTER", "Loan Register", "RECOMMENDED", "Needed to test loan default risk and interest consistency — recommended since not every entity has borrowings."),
        ChecklistItem("INVESTMENT_REGISTER", "Investment Register", "RECOMMENDED", "Needed for fair value and impairment testing — recommended since not every entity holds investments."),
        ChecklistItem("INTERCOMPANY_LEDGER", "Intercompany Ledger", "OPTIONAL", "Needed for intercompany reconciliation — optional since not every entity has related-party transactions."),
        ChecklistItem("INTERCOMPANY_CONFIRMATION", "Intercompany Confirmation", "OPTIONAL", "The counterparty's statement, needed to reconcile against the Intercompany Ledger above."),
    ]

    return items


def coverage_status(rows_valid: int, rows_rejected: int) -> str:
    """Called after any ingestion run to determine this dataset/period's
    coverage status — not a duplicate of ingestion_run.status (which
    describes the run itself), but the resulting *state of coverage*
    for that dataset/period, which may accumulate across multiple runs."""
    if rows_valid == 0:
        return "NOT_UPLOADED"
    if rows_rejected > 0:
        return "PARTIAL"
    return "UPLOADED"
