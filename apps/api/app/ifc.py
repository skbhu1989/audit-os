"""
Phase 12: IFC automated control testing.

Only controls flagged `automatable=true` in the seeded ifc_control table get
a test result derived here. Per Section 50 ("AI cannot independently...
approve management estimates" and the general "AI drafts, humans conclude"
principle), even an automated EFFECTIVE result is a system-derived
observation for the auditor's evaluation, not a final control opinion —
the router layer never marks these APPROVED without a human sign-off.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class ControlTestResult:
    control_id: str
    result: str  # 'EFFECTIVE' | 'EXCEPTION_NOTED'
    detail: str


def test_p2p_vendor_master(duplicate_vendor_pairs: int) -> ControlTestResult:
    if duplicate_vendor_pairs == 0:
        return ControlTestResult("P2P-01", "EFFECTIVE", "No duplicate vendor name pairs identified in the vendor master.")
    return ControlTestResult(
        "P2P-01", "EXCEPTION_NOTED",
        f"{duplicate_vendor_pairs} possible duplicate vendor pair(s) identified — control did not prevent "
        f"near-duplicate vendor master records from being created."
    )


def test_o2c_revenue_gst_completeness(gst_books_vs_gstr1_exceptions: int) -> ControlTestResult:
    if gst_books_vs_gstr1_exceptions == 0:
        return ControlTestResult("O2C-02", "EFFECTIVE", "Books revenue reconciles to GSTR-1 with no exceptions.")
    return ControlTestResult(
        "O2C-02", "EXCEPTION_NOTED",
        f"{gst_books_vs_gstr1_exceptions} exception(s) between books revenue and GSTR-1 — "
        f"revenue-to-GST reconciliation control did not fully operate as designed, or a timing "
        f"difference requires explanation."
    )


def test_r2r_journal_override(high_critical_je_count: int, total_je_count: int) -> ControlTestResult:
    if high_critical_je_count == 0:
        return ControlTestResult(
            "R2R-02", "EFFECTIVE",
            f"None of {total_je_count} journal entries tested showed indicators of management override."
        )
    return ControlTestResult(
        "R2R-02", "EXCEPTION_NOTED",
        f"{high_critical_je_count} of {total_je_count} journal entries scored HIGH/CRITICAL risk "
        f"(round amounts, year-end timing, reversals, or suspense account involvement) — "
        f"warrants investigation of whether the review/approval control operated effectively on these entries."
    )


def test_treasury_tb_balance_direction(flagged_account_count: int) -> ControlTestResult:
    if flagged_account_count == 0:
        return ControlTestResult("TRE-02", "EFFECTIVE", "No trial balance accounts show an unexpected debit/credit direction.")
    return ControlTestResult(
        "TRE-02", "EXCEPTION_NOTED",
        f"{flagged_account_count} account(s) show a balance direction inconsistent with their financial "
        f"statement classification — may indicate a posting error or control gap in the classification review."
    )


def test_tax_statutory_reconciliation(total_statutory_exceptions: int) -> ControlTestResult:
    if total_statutory_exceptions == 0:
        return ControlTestResult("TAX-01", "EFFECTIVE", "GST/TDS/payroll statutory reconciliations show no exceptions.")
    return ControlTestResult(
        "TAX-01", "EXCEPTION_NOTED",
        f"{total_statutory_exceptions} statutory reconciliation exception(s) identified across GST/TDS/payroll — "
        f"the pre-payment reconciliation control did not catch these before the due date, or they reflect "
        f"genuine timing differences requiring explanation."
    )
