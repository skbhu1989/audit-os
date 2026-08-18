"""
Phase 12: CARO clause auto-drafting.

Per Section I ("Never automatically issue the final CARO conclusion") and
the same honesty principle as Phase 7's risk engine: only clause (vii)
Statutory Dues and clause (xi) Fraud Reporting have real ingested data
behind them in this system (GST/TDS/PF/ESI reconciliation, and JE
risk-scoring + duplicate vendor detection, respectively). Every other
clause requires data this system doesn't have yet (fixed asset register,
inventory records, loan agreements, related-party register, CSR tracking,
etc.) and is drafted as such — never a fabricated "no exceptions noted."
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class ClauseDraft:
    data_status: str  # 'DATA_BACKED' | 'INSUFFICIENT_DATA'
    draft_response: str | None
    data_gap_reason: str | None


def draft_statutory_dues_clause(
    gst_exceptions: list[dict], tds_exceptions: list[dict], payroll_exceptions: list[dict]
) -> ClauseDraft:
    total_exceptions = len(gst_exceptions) + len(tds_exceptions) + len(payroll_exceptions)
    material = [
        e for e in (gst_exceptions + tds_exceptions + payroll_exceptions)
        if e.get("risk_level") in ("HIGH", "CRITICAL")
    ]

    if total_exceptions == 0:
        response = (
            "Based on the GST, TDS, and payroll statutory (PF/ESI/PT) reconciliations performed, "
            "the company appears to have been regular in depositing undisputed statutory dues during "
            "the year, and no material amounts were outstanding as at the balance sheet date. "
            "DRAFT — auditor should independently confirm no dues are outstanding for more than "
            "six months as required by the clause, using data beyond what this system's reconciliations "
            "cover (this system checks completeness/accuracy of deposits, not ageing of any residual balance)."
        )
    else:
        listing = "; ".join(
            e.get("reason", e.get("status", "exception")) for e in material[:5]
        ) or "see linked reconciliation exceptions"
        response = (
            f"The GST, TDS, and payroll statutory reconciliations identified {total_exceptions} exception(s), "
            f"of which {len(material)} are HIGH/CRITICAL risk. Notable items: {listing}. "
            f"Auditor should determine which, if any, represent statutory dues outstanding as at the "
            f"balance sheet date (as opposed to timing/reporting differences), and whether any have "
            f"been outstanding for more than six months, before drafting the final clause response. "
            f"DRAFT — NOT a final conclusion."
        )
    return ClauseDraft("DATA_BACKED", response, None)


def draft_fraud_clause(high_critical_je_count: int, total_je_count: int, duplicate_vendor_pairs: int) -> ClauseDraft:
    if total_je_count == 0 and duplicate_vendor_pairs == 0:
        return ClauseDraft(
            "INSUFFICIENT_DATA", None,
            "No journal entries have been risk-scored and no vendor master data is available to assess — "
            "run journal risk scoring and upload a vendor master before this clause can be data-backed."
        )

    if high_critical_je_count == 0 and duplicate_vendor_pairs == 0:
        response = (
            f"Journal entry risk-scoring across {total_je_count} entries and vendor master review identified "
            f"no indicators requiring further fraud investigation. Based on procedures performed, no instance "
            f"of fraud by or on the company was noted or reported during the year. "
            f"DRAFT — this reflects the specific indicators this system checks (journal override patterns, "
            f"duplicate vendor names); it is not a comprehensive fraud audit and does not cover matters "
            f"outside these data points (e.g. whistleblower reports, management representations, external "
            f"correspondence). Auditor must consider these separately before concluding. NOT a final conclusion."
        )
    else:
        response = (
            f"Journal entry risk-scoring identified {high_critical_je_count} of {total_je_count} entries as "
            f"HIGH/CRITICAL risk, and vendor master review identified {duplicate_vendor_pairs} possible "
            f"duplicate vendor pair(s). Per Section AH, these are POTENTIAL FRAUD INDICATORS REQUIRING "
            f"FURTHER INVESTIGATION, not a conclusion that fraud occurred. Auditor should investigate each "
            f"indicator, corroborate with independent evidence, and determine whether any instance meets "
            f"the threshold for reporting under this clause before drafting the final response. "
            f"DRAFT — NOT a final conclusion."
        )
    return ClauseDraft("DATA_BACKED", response, None)


def draft_repayment_of_borrowings_clause(overdue_loans: list[dict], total_borrowings: int) -> ClauseDraft:
    """Clause (ix): Repayment of Borrowings. The first loan data this system
    has ever had (Loans module) — previously this clause was permanently
    INSUFFICIENT_DATA since Phase 12."""
    if total_borrowings == 0:
        return ClauseDraft(
            "INSUFFICIENT_DATA", None,
            "No loan register has been uploaded for this engagement — upload one before this clause can be data-backed."
        )
    if not overdue_loans:
        response = (
            f"Of {total_borrowings} borrowing(s) on record, none show a maturity date past the reporting date "
            f"with a remaining outstanding balance. Based on procedures performed, the company does not appear "
            f"to have defaulted in the repayment of loans or borrowings during the year. "
            f"DRAFT — this reflects only the loans uploaded to this engagement; auditor should confirm the "
            f"loan register is complete before relying on this. NOT a final conclusion."
        )
    else:
        listing = "; ".join(f"{l['lender_or_borrower']} ({l['days_overdue']} days overdue, outstanding {l['outstanding_balance']:,.0f})" for l in overdue_loans[:5])
        response = (
            f"{len(overdue_loans)} of {total_borrowings} borrowing(s) show a maturity date past the reporting "
            f"date with a remaining outstanding balance: {listing}. These require auditor investigation as "
            f"possible defaults before drafting the final clause response — obtain lender correspondence, "
            f"confirm whether the loan has been informally extended, and assess any covenant or cross-default "
            f"implications. DRAFT — NOT a final conclusion."
        )
    return ClauseDraft("DATA_BACKED", response, None)
