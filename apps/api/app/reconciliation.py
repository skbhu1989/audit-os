"""
Phase 6: Statutory reconciliation engine — GST and TDS.

Implements the matching hierarchy from the architecture doc (Section AZ /
Phase 1 Section 10) at MVP scope: L1 (exact document number + GSTIN) and L2
(amount + date + party fallback when document numbers don't align). L3-L6
(fuzzy/AI-assisted matching) are a documented follow-up, not built here —
see the README.

Pure functions over plain dicts/lists, no DB dependency, same design as
ingestion.py and analytics.py: testable in isolation, reusable by a future
async worker for large reconciliation runs.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date


TOLERANCE = 1.0  # rupees; amounts within this are treated as matching


@dataclass
class MatchResult:
    status: str  # MATCHED | PARTIALLY_MATCHED | UNMATCHED
    match_level: str | None
    confidence: float | None
    matching_factors: list[str]
    side_a: dict | None  # None if only present in side B
    side_b: dict | None  # None if only present in side A
    difference: float


def _norm(s) -> str:
    return str(s or "").strip().lower()


def match_invoice_level(side_a: list[dict], side_b: list[dict]) -> list[MatchResult]:
    """side_a/side_b are lists of dicts with keys: invoice_no, gstin, party,
    date, amount. Used for Books-vs-GSTR-1 and Purchase-Register-vs-GSTR-2B.

    L1: exact (invoice_no, gstin) match.
    L2: no L1 match found — fall back to (amount within tolerance + party
        name) within the same reporting period, common when a document
        number is entered inconsistently between books and the portal.
    Unmatched: present in one side only after both levels are tried.
    """
    results: list[MatchResult] = []
    b_by_key = {}
    for b in side_b:
        key = (_norm(b.get("invoice_no")), _norm(b.get("gstin")))
        b_by_key.setdefault(key, []).append(b)

    used_b_ids = set()

    for a in side_a:
        key = (_norm(a.get("invoice_no")), _norm(a.get("gstin")))
        candidates = [c for c in b_by_key.get(key, []) if id(c) not in used_b_ids]
        if candidates:
            b = candidates[0]
            used_b_ids.add(id(b))
            diff = round(float(a["amount"]) - float(b["amount"]), 2)
            status = "MATCHED" if abs(diff) <= TOLERANCE else "PARTIALLY_MATCHED"
            results.append(MatchResult(
                status=status, match_level="L1_EXACT_ID", confidence=1.0 if status == "MATCHED" else 0.9,
                matching_factors=["invoice_no", "gstin"], side_a=a, side_b=b, difference=diff,
            ))
            continue

        # L2 fallback: amount (within tolerance) + party name match, unused only
        l2_candidates = [
            b for b in side_b
            if id(b) not in used_b_ids
            and _norm(b.get("party")) == _norm(a.get("party"))
            and abs(float(b["amount"]) - float(a["amount"])) <= TOLERANCE
        ]
        if l2_candidates:
            b = l2_candidates[0]
            used_b_ids.add(id(b))
            results.append(MatchResult(
                status="MATCHED", match_level="L3_AMOUNT_DATE_PARTY", confidence=0.75,
                matching_factors=["amount", "party_name"], side_a=a, side_b=b, difference=0.0,
            ))
            continue

        results.append(MatchResult(
            status="UNMATCHED", match_level=None, confidence=None,
            matching_factors=[], side_a=a, side_b=None, difference=float(a["amount"]),
        ))

    for b in side_b:
        if id(b) not in used_b_ids:
            results.append(MatchResult(
                status="UNMATCHED", match_level=None, confidence=None,
                matching_factors=[], side_a=None, side_b=b, difference=-float(b["amount"]),
            ))

    return results


def classify_gst_reason(match: MatchResult, side_a_label: str, side_b_label: str) -> str:
    if match.status == "MATCHED":
        return "—"
    if match.side_a is None:
        return f"Present in {side_b_label} but not found in {side_a_label} — investigate completeness"
    if match.side_b is None:
        return f"Present in {side_a_label} but not reported in {side_b_label} — possible reporting gap or timing difference"
    return f"Same document matched but amount differs by {match.difference:,.2f}"


def gst_risk_level(difference: float, materiality: float | None) -> str:
    abs_diff = abs(difference)
    if abs_diff <= TOLERANCE:
        return "LOW"
    if materiality and abs_diff >= materiality:
        return "CRITICAL"
    if materiality and abs_diff >= materiality * 0.25:
        return "HIGH"
    if abs_diff >= 100000:
        return "MEDIUM"
    return "LOW"


# ---------- GSTR-1 vs GSTR-3B period totals ----------

@dataclass
class PeriodReconciliationExure:
    period: str
    books_amount: float
    return_amount: float
    difference: float
    reason: str
    risk: str


def reconcile_period_totals(
    gstr1_totals: dict[str, float], gstr3b_totals: dict[str, float], materiality: float | None
) -> list[PeriodReconciliationExure]:
    out = []
    all_periods = set(gstr1_totals) | set(gstr3b_totals)
    for period in sorted(all_periods):
        a = gstr1_totals.get(period, 0.0)
        b = gstr3b_totals.get(period, 0.0)
        diff = round(a - b, 2)
        if abs(diff) <= TOLERANCE:
            continue
        out.append(PeriodReconciliationExure(
            period=period, books_amount=a, return_amount=b, difference=diff,
            reason="GSTR-1 turnover does not agree with GSTR-3B for the period — check credit notes, RCM, and amendments",
            risk=gst_risk_level(diff, materiality),
        ))
    return out


# ---------- TDS reconciliation ----------

@dataclass
class TdsSectionResult:
    section: str
    deducted: float
    paid: float
    reported: float
    status: str
    interest_exposure: float


def reconcile_tds(
    deducted_by_section: dict[str, float],
    paid_by_section: dict[str, float],
    reported_by_section: dict[str, float],
    months_overdue_by_section: dict[str, int] | None = None,
) -> list[TdsSectionResult]:
    """Interest exposure uses a simplified flat 1.5%/month on the shortfall
    (Sec 201(1A) uses 1%/month for late deduction, 1.5%/month for late
    payment — collapsed to the higher, more conservative rate here since we
    don't yet distinguish which failure mode occurred; a real implementation
    should look this up from the versioned rule engine, not a constant)."""
    months_overdue_by_section = months_overdue_by_section or {}
    sections = sorted(set(deducted_by_section) | set(paid_by_section) | set(reported_by_section))
    out = []
    for section in sections:
        deducted = deducted_by_section.get(section, 0.0)
        paid = paid_by_section.get(section, 0.0)
        reported = reported_by_section.get(section, 0.0)

        if abs(deducted - paid) <= TOLERANCE and abs(deducted - reported) <= TOLERANCE:
            status = "Matched"
            shortfall = 0.0
        elif deducted > paid + TOLERANCE:
            status = "Deduction without full payment — interest exposure under Sec 201(1A)"
            shortfall = deducted - paid
        elif paid > deducted + TOLERANCE:
            status = "Payment exceeds ledger deduction — possible unrecorded liability or misclassified challan"
            shortfall = 0.0
        elif abs(reported - deducted) > TOLERANCE:
            status = "Return does not agree with the deduction ledger — check deductee-level reporting"
            shortfall = 0.0
        else:
            status = "Matched"
            shortfall = 0.0

        months = months_overdue_by_section.get(section, 1) if shortfall > 0 else 0
        interest = round(shortfall * 0.015 * months, 2)

        out.append(TdsSectionResult(
            section=section, deducted=deducted, paid=paid, reported=reported,
            status=status, interest_exposure=interest,
        ))
    return out


# ---------- Payroll statutory reconciliation (PF/ESI/PT) ----------
# Simpler than TDS: liability (from payroll register) vs paid (from challan),
# no separate "reported" (ECR/return) side yet — see Phase 11 README for
# what a fuller 3-way reconciliation would still need.

@dataclass
class PayrollStatutoryResult:
    scheme: str
    period: str
    liability: float
    paid: float
    difference: float
    status: str


def reconcile_payroll_statutory(
    scheme: str, liability_by_period: dict[str, float], paid_by_period: dict[str, float]
) -> list[PayrollStatutoryResult]:
    out = []
    for period in sorted(set(liability_by_period) | set(paid_by_period)):
        liability = liability_by_period.get(period, 0.0)
        paid = paid_by_period.get(period, 0.0)
        diff = round(liability - paid, 2)
        if abs(diff) <= TOLERANCE:
            status = "Matched"
        elif diff > 0:
            status = f"Unpaid {scheme} liability — challan payment short or missing"
        else:
            status = f"Challan payment exceeds recorded {scheme} liability — possible unrecorded payroll or misclassified challan"
        out.append(PayrollStatutoryResult(scheme=scheme, period=period, liability=liability, paid=paid, difference=diff, status=status))
    return out
