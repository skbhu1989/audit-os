"""
Phase 5: Trial Balance mapping suggestions + GL/JE risk analytics.

Same design principle as ingestion.py — pure functions over plain data, no
DB/FastAPI dependency, so the scoring logic is unit-testable and reusable by
a future async worker. Per the architecture doc's Rule Engine principle
(Section B): this is deterministic scoring, not an LLM guessing at risk —
an LLM layer can narrate *why* a score is what it is, but the number itself
comes from here.
"""
from __future__ import annotations
import re
from datetime import date
from dataclasses import dataclass, field


# ---------- Trial Balance FS-line mapping suggestions ----------
# Ordered rules over Schedule III-style captions. First match wins;
# keywords are checked as substrings of the normalized (lowercased) ledger
# name. This is a starting rule set — real firms will maintain their own
# via the versioned rule_version mechanism from Phase 2, not hardcode it
# here forever, but a sensible default beats an empty one.

FS_MAPPING_RULES = [
    # (keywords, fs_statement, fs_line, note_ref, is_suspense)
    (["suspense"], "UNMAPPED", None, None, True),
    (["share capital"], "BALANCE_SHEET", "Balance Sheet — Equity", "Share Capital", False),
    (["reserves", "surplus", "retained earning", "general reserve"], "BALANCE_SHEET", "Balance Sheet — Equity", "Reserves and Surplus", False),
    (["debenture", "term loan", "borrowing", "loan from"], "BALANCE_SHEET", "Balance Sheet — Non-current Liabilities", "Borrowings", False),
    (["deferred tax liab"], "BALANCE_SHEET", "Balance Sheet — Non-current Liabilities", "Deferred Tax Liabilities", False),
    (["trade payable", "sundry creditor", "creditors for"], "BALANCE_SHEET", "Balance Sheet — Current Liabilities", "Trade Payables", False),
    (["gst payable", "gst output", "duties and taxes", "tax payable"], "BALANCE_SHEET", "Balance Sheet — Current Liabilities", "Other Current Liabilities", False),
    (["tds payable", "tds deducted"], "BALANCE_SHEET", "Balance Sheet — Current Liabilities", "Other Current Liabilities", False),
    (["provision"], "BALANCE_SHEET", "Balance Sheet — Current Liabilities", "Short-term Provisions", False),
    (["capital work", "cwip"], "BALANCE_SHEET", "Balance Sheet — Non-current Assets", "Capital Work-in-Progress", False),
    (["property", "plant and machinery", "furniture", "vehicle", "fixed asset", "office equipment", "computer"], "BALANCE_SHEET", "Balance Sheet — Non-current Assets", "Property, Plant and Equipment", False),
    (["investment"], "BALANCE_SHEET", "Balance Sheet — Non-current Assets", "Investments", False),
    (["deferred tax asset"], "BALANCE_SHEET", "Balance Sheet — Non-current Assets", "Deferred Tax Assets", False),
    (["trade receivable", "sundry debtor", "debtors for"], "BALANCE_SHEET", "Balance Sheet — Current Assets", "Trade Receivables", False),
    (["cash", "bank account", "bank balance", "petty cash"], "BALANCE_SHEET", "Balance Sheet — Current Assets", "Cash and Bank Balances", False),
    (["inventor", "stock"], "BALANCE_SHEET", "Balance Sheet — Current Assets", "Inventories", False),
    (["revenue from operation", "sales", "turnover"], "PROFIT_AND_LOSS", "P&L — Revenue", "Revenue from Operations", False),
    (["other income", "interest income", "dividend income"], "PROFIT_AND_LOSS", "P&L — Other Income", "Other Income", False),
    (["purchase"], "PROFIT_AND_LOSS", "P&L — Expenses", "Purchases", False),
    (["employee benefit", "salary", "salaries", "wages", "bonus", "gratuity"], "PROFIT_AND_LOSS", "P&L — Expenses", "Employee Benefit Expense", False),
    (["finance cost", "interest expense", "bank charges"], "PROFIT_AND_LOSS", "P&L — Expenses", "Finance Costs", False),
    (["depreciation", "amortisation", "amortization"], "PROFIT_AND_LOSS", "P&L — Expenses", "Depreciation and Amortisation", False),
]


@dataclass
class MappingSuggestion:
    fs_statement: str
    fs_line: str | None
    note_ref: str | None
    is_suspense: bool
    confidence: float
    matched_keyword: str | None


def suggest_fs_mapping(ledger_name: str) -> MappingSuggestion:
    """Scans ALL rules and picks the LONGEST matching keyword, not simply the
    first rule in list order. First-match-wins is fragile once a ledger name
    contains multiple category-suggestive words — e.g. 'Purchase of
    Stock-in-Trade' contains both 'stock' (Balance Sheet / Inventories) and
    'purchase' (P&L / Expenses); the correct classification (an expense line)
    only wins if longer/more specific matches are preferred over shorter,
    more generic ones. Caught by running this against real ledger names, not
    by inspecting the rule table.
    """
    name = ledger_name.lower()
    best: tuple[list, str] | None = None  # (rule_tuple, matched_keyword)
    for rule in FS_MAPPING_RULES:
        keywords = rule[0]
        for kw in keywords:
            if kw in name:
                if best is None or len(kw) > len(best[1]):
                    best = (rule, kw)
    if best is None:
        return MappingSuggestion("UNMAPPED", None, None, False, 0.0, None)

    (keywords, fs_statement, fs_line, note_ref, is_suspense), kw = best
    confidence = min(0.95, 0.55 + 0.04 * len(kw.split()) + 0.01 * len(kw))
    return MappingSuggestion(fs_statement, fs_line, note_ref, is_suspense, round(confidence, 2), kw)


# ---------- Trial Balance balance-direction flags ----------

DEBIT_NORMAL_STATEMENTS_LINES = {
    "Balance Sheet — Non-current Assets", "Balance Sheet — Current Assets", "P&L — Expenses",
}
CREDIT_NORMAL_LINES = {
    "Balance Sheet — Equity", "Balance Sheet — Non-current Liabilities",
    "Balance Sheet — Current Liabilities", "P&L — Revenue", "P&L — Other Income",
}


def tb_balance_flag(fs_line: str | None, debit: float, credit: float, tolerance: float = 1.0) -> str | None:
    """Flags a line whose actual balance direction contradicts what its FS
    classification implies — Section 16's 'negative receivables, negative
    payables, debit liabilities, credit expenses' checks, generalized."""
    if fs_line is None:
        return None
    net = debit - credit
    if abs(net) <= tolerance:
        return None
    if fs_line in DEBIT_NORMAL_STATEMENTS_LINES and net < 0:
        return f"Unexpected credit balance in a normally-debit account ('{fs_line}') — e.g. a negative receivable or credit balance in an asset/expense line"
    if fs_line in CREDIT_NORMAL_LINES and net > 0:
        return f"Unexpected debit balance in a normally-credit account ('{fs_line}') — e.g. a negative payable or debit balance in a liability/income line"
    return None


# ---------- Journal Entry risk scoring ----------

MANAGEMENT_TITLES = re.compile(r"\b(MD|CEO|CFO|COO|Director|Partner|Promoter)\b", re.IGNORECASE)
REVERSAL_WORDS = re.compile(r"revers|write[- ]?back|write[- ]?off", re.IGNORECASE)

RISK_WEIGHTS = {
    "round_number": 15,
    "weekend": 15,
    "year_end": 20,
    "management_poster": 20,
    "reversal_narration": 15,
    "suspense_account": 15,
    "above_materiality": 20,
}


@dataclass
class JournalRiskResult:
    score: float
    level: str
    reasons: list[str] = field(default_factory=list)


def score_journal(
    posted_date: date,
    posted_by: str | None,
    narration: str | None,
    amount: float,
    debit_account_name: str,
    credit_account_name: str,
    reporting_date: date,
    performance_materiality: float | None,
) -> JournalRiskResult:
    score = 0.0
    reasons: list[str] = []

    if amount > 0 and amount % 50000 == 0:
        score += RISK_WEIGHTS["round_number"]
        reasons.append("Round-number amount")

    if posted_date.weekday() >= 5:  # Sat=5, Sun=6
        score += RISK_WEIGHTS["weekend"]
        reasons.append("Posted on a weekend")

    days_before_reporting = (reporting_date - posted_date).days
    if 0 <= days_before_reporting <= 4:
        score += RISK_WEIGHTS["year_end"]
        reasons.append("Posted in the final days of the financial year")

    if posted_by and MANAGEMENT_TITLES.search(posted_by):
        score += RISK_WEIGHTS["management_poster"]
        reasons.append("Posted directly by senior management (override risk)")

    if narration and REVERSAL_WORDS.search(narration):
        score += RISK_WEIGHTS["reversal_narration"]
        reasons.append("Reversal / write-back / write-off entry")

    if "suspense" in debit_account_name.lower() or "suspense" in credit_account_name.lower():
        score += RISK_WEIGHTS["suspense_account"]
        reasons.append("Involves a Suspense Account")

    if performance_materiality and amount >= performance_materiality:
        score += RISK_WEIGHTS["above_materiality"]
        reasons.append(f"Amount ({amount:,.0f}) is at or above performance materiality ({performance_materiality:,.0f})")

    score = min(100.0, score)
    if score <= 20:
        level = "LOW"
    elif score <= 40:
        level = "MODERATE"
    elif score <= 60:
        level = "MEDIUM"
    elif score <= 80:
        level = "HIGH"
    else:
        level = "CRITICAL"

    if not reasons:
        reasons = ["No anomaly indicators identified"]

    return JournalRiskResult(score, level, reasons)
