"""
Phase 7: Multi-category Audit Risk Engine (Section BN).

Computes a 0-100 risk score per FS area (Revenue, Receivables, Payables,
Cash, GST, TDS, Fraud Indicators, Statutory Compliance), bucketed into the
same LOW/MODERATE/MEDIUM/HIGH/CRITICAL scale used everywhere else in this
system (risk_level enum, Section 23's scoring pattern).

DESIGN PRINCIPLE — the one that matters most here: a category with no
underlying data source does NOT get a fabricated LOW score. Section BN lists
14 categories (Revenue, Receivables, Inventory, Payables, Cash, Tax, GST,
TDS, Related Parties, Fraud, Going Concern, Financial Instruments, Estimates,
IFC, Statutory Compliance); this system has real ingested/computed data
behind roughly half of them. The other half — Inventory (no inventory data
ingested), Related Parties (is_related_party is never populated), Going
Concern (no cash-flow/covenant tracking), Financial Instruments, Estimates,
IFC, and broad Income Tax — return INSUFFICIENT_DATA, not a silently
optimistic score. A blank field that says "no data" is honest; a LOW score
computed from nothing is a false assurance, and false assurance is worse
than no answer in an audit tool.
"""
from __future__ import annotations
from dataclasses import dataclass, field


SEVERITY_WEIGHT = {"LOW": 5, "MODERATE": 10, "MEDIUM": 15, "HIGH": 30, "CRITICAL": 50}


def _bucket(score: float) -> str:
    if score <= 20:
        return "LOW"
    if score <= 40:
        return "MODERATE"
    if score <= 60:
        return "MEDIUM"
    if score <= 80:
        return "HIGH"
    return "CRITICAL"


@dataclass
class CategoryRisk:
    category: str
    status: str  # 'SCORED' | 'INSUFFICIENT_DATA'
    score: float | None = None
    level: str | None = None
    factors: list[str] = field(default_factory=list)
    data_gap_reason: str | None = None


def score_gst(exceptions: list[dict]) -> CategoryRisk:
    if not exceptions:
        return CategoryRisk("GST", "SCORED", 0.0, "LOW", ["No GST reconciliation exceptions found"])
    raw = sum(SEVERITY_WEIGHT.get(e["risk_level"], 0) for e in exceptions)
    score = round(min(100.0, raw), 1)
    factors = [f"{len(exceptions)} reconciliation exception(s) across Books/GSTR-1/GSTR-2B/GSTR-3B"]
    by_level = {}
    for e in exceptions:
        by_level[e["risk_level"]] = by_level.get(e["risk_level"], 0) + 1
    factors.append(", ".join(f"{v}x {k}" for k, v in sorted(by_level.items())))
    return CategoryRisk("GST", "SCORED", score, _bucket(score), factors)


def score_tds(exceptions: list[dict]) -> CategoryRisk:
    if not exceptions:
        return CategoryRisk("TDS", "SCORED", 0.0, "LOW", ["No TDS reconciliation exceptions found"])
    total_interest = sum(e.get("interest_exposure", 0) or 0 for e in exceptions)
    raw = len(exceptions) * 30 + min(50.0, total_interest / 100)  # interest scaled, capped contribution
    score = round(min(100.0, raw), 1)
    factors = [f"{len(exceptions)} section(s) with a deduction/payment/return exception",
               f"Aggregate estimated interest exposure ₹{total_interest:,.2f}"]
    return CategoryRisk("TDS", "SCORED", score, _bucket(score), factors)


def score_revenue(gst_books_vs_gstr1_exceptions: list[dict], revenue_tb_flags: list[str]) -> CategoryRisk:
    if not gst_books_vs_gstr1_exceptions and not revenue_tb_flags:
        return CategoryRisk("Revenue", "SCORED", 0.0, "LOW", ["No GST completeness exceptions or TB anomalies on revenue accounts"])
    raw = sum(SEVERITY_WEIGHT.get(e["risk_level"], 0) for e in gst_books_vs_gstr1_exceptions) + len(revenue_tb_flags) * 20
    score = round(min(100.0, raw), 1)
    factors = []
    if gst_books_vs_gstr1_exceptions:
        factors.append(f"{len(gst_books_vs_gstr1_exceptions)} Books-vs-GSTR-1 exception(s) — revenue completeness/accuracy proxy")
    if revenue_tb_flags:
        factors.extend(revenue_tb_flags)
    return CategoryRisk("Revenue", "SCORED", score, _bucket(score), factors)


def score_receivables(tb_flags: list[str], unmatched_sales_count: int) -> CategoryRisk:
    if not tb_flags and unmatched_sales_count == 0:
        return CategoryRisk("Receivables", "SCORED", 0.0, "LOW", ["No balance-direction anomalies or unmatched sales invoices"])
    raw = len(tb_flags) * 25 + unmatched_sales_count * 10
    score = round(min(100.0, raw), 1)
    factors = list(tb_flags)
    if unmatched_sales_count:
        factors.append(f"{unmatched_sales_count} sales invoice(s) not confirmed against GSTR-1 (completeness proxy)")
    return CategoryRisk("Receivables", "SCORED", score, _bucket(score), factors,
                         data_gap_reason="Ageing-based confirmation and ECL data not yet available — this score reflects only balance-direction and GST-completeness signals, not a full receivables risk assessment.")


def score_payables(tb_flags: list[str], unmatched_purchase_count: int) -> CategoryRisk:
    if not tb_flags and unmatched_purchase_count == 0:
        return CategoryRisk("Payables", "SCORED", 0.0, "LOW", ["No balance-direction anomalies or unmatched purchase invoices"])
    raw = len(tb_flags) * 25 + unmatched_purchase_count * 10
    score = round(min(100.0, raw), 1)
    factors = list(tb_flags)
    if unmatched_purchase_count:
        factors.append(f"{unmatched_purchase_count} purchase invoice(s) not confirmed against GSTR-2B (possible unrecorded liability / ITC exposure)")
    return CategoryRisk("Payables", "SCORED", score, _bucket(score), factors,
                         data_gap_reason="Subsequent-payment-based unrecorded liability search not yet built — this score reflects only balance-direction and GST-completeness signals.")


def score_cash(tb_flags: list[str], bank_txn_count: int) -> CategoryRisk:
    if not tb_flags:
        return CategoryRisk(
            "Cash & Bank", "SCORED", 0.0, "LOW", ["No balance-direction anomalies on cash/bank accounts"],
            data_gap_reason=f"Bank reconciliation matching engine not yet built — {bank_txn_count} bank transaction(s) "
                             f"are recorded but not matched against the ledger, so this score cannot reflect unreconciled items."
        )
    raw = len(tb_flags) * 30
    score = round(min(100.0, raw), 1)
    return CategoryRisk("Cash & Bank", "SCORED", score, _bucket(score), list(tb_flags),
                         data_gap_reason="Bank reconciliation matching engine not yet built — score reflects only TB balance-direction signals.")


def score_fraud_indicators(high_critical_je_count: int, total_je_count: int, duplicate_vendor_pairs: int) -> CategoryRisk:
    if total_je_count == 0 and duplicate_vendor_pairs == 0:
        return CategoryRisk("Fraud Indicators", "INSUFFICIENT_DATA", data_gap_reason="No journal entries or vendor master data available to assess.")
    raw = high_critical_je_count * 25 + duplicate_vendor_pairs * 20
    score = round(min(100.0, raw), 1)
    factors = [f"{high_critical_je_count} of {total_je_count} journal entries scored HIGH/CRITICAL",
               f"{duplicate_vendor_pairs} possible duplicate vendor pair(s)"]
    return CategoryRisk("Fraud Indicators", "SCORED", score, _bucket(score), factors,
                         data_gap_reason="Reflects journal risk-scoring and vendor-name similarity only — "
                                         "does not include approval-limit, split-transaction, or Benford's Law analysis (not yet built). "
                                         "Per Section AH, a HIGH/CRITICAL score here is a POTENTIAL FRAUD INDICATOR REQUIRING "
                                         "FURTHER INVESTIGATION, never a conclusion that fraud has occurred.")


def score_statutory_compliance(gst_risk: CategoryRisk, tds_risk: CategoryRisk) -> CategoryRisk:
    scores = [r.score for r in (gst_risk, tds_risk) if r.status == "SCORED" and r.score is not None]
    if not scores:
        return CategoryRisk("Statutory Compliance", "INSUFFICIENT_DATA", data_gap_reason="No GST or TDS reconciliation has been run yet.")
    score = max(scores)  # the worst-scoring statutory area drives overall compliance risk, not an average that dilutes it
    return CategoryRisk(
        "Statutory Compliance", "SCORED", score, _bucket(score),
        [f"GST: {gst_risk.level or 'no data'}", f"TDS: {tds_risk.level or 'no data'}"],
        data_gap_reason="Covers GST and TDS only — PF/ESI/PT, Income Tax, and MCA/ROC reconciliation are not yet built (Sections 70-73)."
    )


NO_DATA_CATEGORIES = [
    ("Inventory", "No inventory data has been ingested for this engagement (no inventory parser built yet)."),
    ("Related Parties", "Related-party identification is not yet populated — vendor/customer.is_related_party exists in the schema but nothing writes to it yet."),
    ("Going Concern", "No cash-flow, debt-maturity, or covenant data is tracked yet."),
    ("Financial Instruments", "No loan/investment classification or ECL engine is built yet."),
    ("Estimates", "No estimates/provisions testing module is built yet."),
    ("IFC", "No internal control testing module is built yet."),
    ("Income Tax (broad)", "Only TDS is reconciled; income tax provision, advance tax, and AIS/26AS reconciliation are not yet built."),
]


def all_category_risks(
    gst_exceptions: list[dict], tds_exceptions: list[dict],
    gst_books_vs_gstr1_exceptions: list[dict], revenue_tb_flags: list[str],
    receivables_tb_flags: list[str], unmatched_sales_count: int,
    payables_tb_flags: list[str], unmatched_purchase_count: int,
    cash_tb_flags: list[str], bank_txn_count: int,
    high_critical_je_count: int, total_je_count: int, duplicate_vendor_pairs: int,
) -> list[CategoryRisk]:
    gst = score_gst(gst_exceptions)
    tds = score_tds(tds_exceptions)
    results = [
        gst, tds,
        score_revenue(gst_books_vs_gstr1_exceptions, revenue_tb_flags),
        score_receivables(receivables_tb_flags, unmatched_sales_count),
        score_payables(payables_tb_flags, unmatched_purchase_count),
        score_cash(cash_tb_flags, bank_txn_count),
        score_fraud_indicators(high_critical_je_count, total_je_count, duplicate_vendor_pairs),
    ]
    results.append(score_statutory_compliance(gst, tds))
    for name, reason in NO_DATA_CATEGORIES:
        results.append(CategoryRisk(name, "INSUFFICIENT_DATA", data_gap_reason=reason))
    return results
