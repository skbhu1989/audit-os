"""
AI Audit Assistant — intent routing and structured answer construction.

IMPORTANT SCOPING NOTE (see PHASE10 README): this module does NOT call an
LLM. Per the architecture doc's layered design (Section B — rule engine /
RAG / analytics, with the LLM only for interpretation), the actual
"intelligence" here is deterministic: keyword-based intent detection, real
SQL queries against the engagement's data, and template-based structuring of
the response. This sandbox has no configured LLM API credentials, so rather
than fake a call or silently skip the requirement, the honest scope is: build
everything an LLM orchestration layer would call *into* — real data
retrieval, real calculation, correctly-cited sources — and leave the LLM
call itself as a documented, swappable next step (see AIAnswer.narrate_with_llm
being absent — deliberately not stubbed with fake text).

Every answer is grounded in a specific data query; if no intent matches or
the matched intent has no data to work with, the no-hallucination fallback
(Section 49/BV) fires: "INSUFFICIENT INFORMATION TO CONCLUDE."
"""
from __future__ import annotations
import re
import difflib
from dataclasses import dataclass, field


@dataclass
class AIAnswer:
    answer: str
    data_used: str
    calculation: str
    source: str
    standard: str
    evidence: str
    implication: str
    procedure: str


# ---------- source citations ----------
# Real, correctly-attributed standard/section references only — consistent
# with the no-hallucination policy, nothing here is invented. Tagged with
# source type per the Source Hierarchy (Section BT) so the caller can
# distinguish mandatory law from guidance.

CITATIONS = {
    "duplicate_vendor": ("STATUTE/GUIDANCE", "SA 240 (fraud risk factors); IFC — Procure-to-Pay master data control"),
    "journal_risk": ("AUDITING_STANDARD", "SA 240 (management override); SA 330 (response to assessed risk)"),
    "gst_reconciliation": ("STATUTE", "CGST Act 2017 & Rules; SA 500 (audit evidence)"),
    "tds_reconciliation": ("STATUTE", "Income Tax Act 1961, Chapter XVII-B, Sec 201(1A); SA 250"),
    "trial_balance": ("AUDITING_STANDARD", "SA 500; Schedule III, Companies Act 2013"),
    "working_papers": ("AUDITING_STANDARD", "SA 230 (Audit Documentation)"),
}


# ---------- amount parsing (Indian numbering: lakh/crore) ----------

def parse_indian_amount(text: str) -> float | None:
    """Extracts an amount from phrases like '25 lakh', '₹1.2 crore', '500000'."""
    text = text.lower()
    m = re.search(r"(?:₹|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(lakh|lac|crore|cr)\b", text)
    if m:
        num = float(m.group(1).replace(",", ""))
        multiplier = 100000 if m.group(2) in ("lakh", "lac") else 10000000
        return num * multiplier
    m2 = re.search(r"(?:₹|rs\.?|inr)\s*([\d,]{4,})", text)
    if m2:
        return float(m2.group(1).replace(",", ""))
    return None


# ---------- intent detection ----------

def detect_intent(question: str) -> str | None:
    q = question.lower()
    if "duplicate" in q and "vendor" in q:
        return "duplicate_vendor"
    if ("year" in q and "end" in q) or "31 march" in q or "year-end" in q:
        return "journal_year_end"
    if "unusual" in q and ("journal" in q or "entries" in q or "je" in q):
        return "journal_risk"
    if "risk" in q and ("journal" in q or "je" in q):
        return "journal_risk"
    if "gst" in q and ("reconcil" in q or "turnover" in q or "mismatch" in q):
        return "gst_reconciliation"
    if "tds" in q and ("correct" in q or "reconcil" in q or "check" in q or "short" in q):
        return "tds_reconciliation"
    if "trial balance" in q and ("tie" in q or "status" in q or "map" in q):
        return "trial_balance"
    if "working paper" in q and "status" in q:
        return "working_papers"
    if "payment" in q and ("above" in q or "large" in q or "more than" in q):
        return "large_payments"
    return None


# ---------- answer builders (pure functions over pre-fetched data) ----------

def build_duplicate_vendor_answer(vendors: list[dict]) -> AIAnswer | None:
    """vendors: [{'name': str, 'id': str}, ...]. Uses difflib on normalized
    names — the same class of check Phase 4's README flagged as a gap
    (exact-match-only duplicate detection); this closes that gap for the
    read-only assistant path without changing the ingestion pipeline."""
    pairs = []
    for i, a in enumerate(vendors):
        for b in vendors[i + 1:]:
            ratio = difflib.SequenceMatcher(None, a["name"].lower(), b["name"].lower()).ratio()
            # 0.6 initially seemed reasonable but produced false positives on
            # unrelated vendors sharing a common business-type word (e.g. two
            # different "... Traders" companies scored 0.72) — caught by
            # testing against a realistic vendor list, not by eyeballing the
            # threshold. 0.75 still catches the intended near-duplicate
            # ("ABC Traders" vs "ABC Trader's Co", 0.85) while excluding the
            # coincidental-word-overlap false positives.
            if ratio >= 0.75 and a["name"].lower() != b["name"].lower():
                pairs.append((a["name"], b["name"], round(ratio, 2)))

    if not pairs:
        return None

    source_type, citation = CITATIONS["duplicate_vendor"]
    return AIAnswer(
        answer=f"{len(pairs)} vendor name pair(s) show high similarity, indicating possible duplicate master records.",
        data_used=", ".join(f"'{a}' vs '{b}' (similarity {r})" for a, b, r in pairs),
        calculation="Normalized string similarity (difflib SequenceMatcher ratio) across all vendor pairs in the engagement, threshold 0.75.",
        source=source_type,
        standard=citation,
        evidence="Vendor master extract; no KYC/PAN cross-check performed at this similarity threshold.",
        implication="Risk of duplicate payment, split-vendor approval evasion, or a fictitious vendor disguised as a near-duplicate of a real one.",
        procedure="Request vendor KYC/PAN/bank account details for each pair; confirm whether one record should be deactivated and its transaction history reassigned.",
    )


def build_journal_risk_answer(journals: list[dict], filter_desc: str) -> AIAnswer | None:
    """journals: [{'id','date','user','amount','level','reasons'}, ...] already filtered by caller."""
    if not journals:
        return None
    source_type, citation = CITATIONS["journal_risk"]
    listing = "; ".join(f"{j['id']} (₹{j['amount']:,.0f}, {j['level']})" for j in journals[:10])
    return AIAnswer(
        answer=f"{len(journals)} journal entries match: {filter_desc}.",
        data_used=listing,
        calculation="Deterministic risk scoring: round-number amount, weekend/year-end posting, management poster, reversal narration, suspense account involvement, materiality — see Phase 5 analytics engine for weights.",
        source=source_type,
        standard=citation,
        evidence="Journal register with posting date, user, narration, and computed risk reasons.",
        implication="Elevated risk of management override, cut-off error, or manual manipulation of the general ledger.",
        procedure="Obtain business rationale and supporting documentation for each entry; for HIGH/CRITICAL entries, corroborate with independent evidence (bank statement, contract, board minutes).",
    )


def build_gst_reconciliation_answer(exceptions: list[dict]) -> AIAnswer | None:
    if not exceptions:
        return None
    source_type, citation = CITATIONS["gst_reconciliation"]
    total_diff = sum(abs(e.get("difference") or 0) for e in exceptions)
    listing = "; ".join(
        f"{e['recon_type']}: {e.get('document_no') or e.get('period') or '(unspecified)'} "
        f"(diff ₹{(e.get('difference') or 0):,.2f}, {e['risk_level']})"
        for e in exceptions[:10]
    )
    return AIAnswer(
        answer=f"{len(exceptions)} GST reconciliation exception(s) found, aggregate absolute difference ₹{total_diff:,.2f}.",
        data_used=listing,
        calculation="Books/GSTR-1/GSTR-2B/GSTR-3B matched at document level (L1 exact + amount/party fallback) and at period level for GSTR-1 vs GSTR-3B; unmatched/partially-matched items reported as exceptions.",
        source=source_type,
        standard=citation,
        evidence="Sales/purchase register, GSTR-1, GSTR-2B, GSTR-3B extracts as uploaded to this engagement.",
        implication="Potential revenue/ITC completeness or accuracy issue, and/or GST short-payment exposure depending on direction of the difference.",
        procedure="Raise a client query for each exception; obtain the reconciliation statement supporting the annual GSTR-9C filing.",
    )


def build_tds_reconciliation_answer(exceptions: list[dict]) -> AIAnswer | None:
    if not exceptions:
        return None
    source_type, citation = CITATIONS["tds_reconciliation"]
    listing = "; ".join(f"Sec {e['section']}: {e['reason']}" for e in exceptions)
    return AIAnswer(
        answer=f"{len(exceptions)} TDS section(s) show a deduction/payment/return exception.",
        data_used=listing,
        calculation="Section-wise aggregation of TDS ledger (deducted) vs challan (paid) vs return (reported); interest exposure at a simplified flat 1.5%/month on any shortfall.",
        source=source_type,
        standard=citation,
        evidence="TDS ledger, challan register, and TDS return extracts as uploaded to this engagement.",
        implication="Interest exposure under Sec 201(1A); possible disallowance under Sec 40(a)(ia) if short/non-deduction is not remedied.",
        procedure="Recompute interest precisely (distinguishing late-deduction 1%/month from late-payment 1.5%/month, which this simplified check does not); confirm subsequent payment or revised filing.",
    )


def build_trial_balance_answer(tb_ties: bool, total_debit: float, total_credit: float, unmapped_count: int) -> AIAnswer:
    source_type, citation = CITATIONS["trial_balance"]
    tie_text = "ties" if tb_ties else "DOES NOT TIE"
    return AIAnswer(
        answer=f"Trial balance {tie_text} — total debit ₹{total_debit:,.2f}, total credit ₹{total_credit:,.2f}. "
               f"{unmapped_count} ledger(s) remain unmapped to a financial statement line (pending human approval).",
        data_used="Latest trial_balance_line per account, and account.mapped_by status, for this engagement.",
        calculation="Sum of latest debit/credit balance per ledger account; unmapped count = accounts where mapped_by IS NULL.",
        source=source_type,
        standard=citation,
        evidence="Trial balance upload(s) and the FS-line mapping approval trail.",
        implication="An untied trial balance blocks financial statement preparation; unmapped accounts cannot be relied on for FS line-item testing until approved.",
        procedure="If untied, investigate the difference before proceeding. For unmapped accounts, review and approve or override the system's FS-line suggestions.",
    )


def build_no_data_answer(reason: str) -> AIAnswer:
    return AIAnswer(
        answer="INSUFFICIENT INFORMATION TO CONCLUDE.",
        data_used="None available for this query.",
        calculation="N/A",
        source="N/A",
        standard="N/A",
        evidence="N/A",
        implication="N/A",
        procedure=f"INFORMATION REQUIRED: {reason}",
    )
