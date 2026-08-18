"""
AP Reconciliation (Section 55) and AR Reconciliation (Section 56).

Scoped honestly: this system has no PO/GRN ingestion (Section 55's full
"PO → GRN → Invoice → Books → GST → TDS → Payment" chain needs data this
system doesn't collect yet), so AP reconciliation here covers what's
actually computable from ingested data — duplicate invoice detection,
ageing, and subsequent-payment matching against the bank statement. AR is
the mirror image with subsequent receipts.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date

TOLERANCE = 1.0
PAYMENT_MATCH_WINDOW_DAYS = 45  # a payment/receipt reasonably close to an invoice date is worth flagging as likely-related


@dataclass
class DuplicateInvoicePair:
    invoice_a: str
    invoice_b: str
    party: str
    amount: float
    date_diff_days: int
    confidence: str  # 'HIGH' | 'MEDIUM'


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def detect_duplicate_invoices(invoices: list[dict]) -> list[DuplicateInvoicePair]:
    """invoices: [{'invoice_no','party','amount','invoice_date'}]. Flags pairs
    with the same party + same amount within a short date window — the
    classic duplicate-payment risk pattern (Section 80), distinct from
    Phase 10's duplicate *vendor name* detection (this is duplicate
    *invoices*, which can happen even with a single correctly-named vendor)."""
    pairs = []
    for i, a in enumerate(invoices):
        for b in invoices[i + 1:]:
            if a["invoice_no"].lower() == b["invoice_no"].lower():
                continue  # same invoice number is not a "possible duplicate," it's the same document
            if _norm(a["party"]) != _norm(b["party"]):
                continue
            if abs(a["amount"] - b["amount"]) > TOLERANCE:
                continue
            days = abs((a["invoice_date"] - b["invoice_date"]).days)
            if days > 60:
                continue
            confidence = "HIGH" if days <= 7 else "MEDIUM"
            pairs.append(DuplicateInvoicePair(a["invoice_no"], b["invoice_no"], a["party"], a["amount"], days, confidence))
    return pairs


@dataclass
class AgeingBucket:
    party: str
    invoice_no: str
    outstanding: float
    age_days: int
    bucket: str


def compute_ageing(invoices: list[dict], payments_or_receipts: list[dict], as_of: date) -> list[AgeingBucket]:
    """invoices: [{'invoice_no','party','amount','invoice_date'}]
    payments_or_receipts: [{'party','amount','txn_date'}] — matched to invoices
    by party + amount within the payment window; unmatched invoices are
    treated as fully outstanding. This is a simplification (real cash
    application would match at the invoice level via a reference number,
    not built here) — stated in the README, not hidden."""
    used_payment_idx = set()
    out = []
    for inv in invoices:
        matched = False
        for idx, p in enumerate(payments_or_receipts):
            if idx in used_payment_idx:
                continue
            if _norm(p["party"]) != _norm(inv["party"]):
                continue
            if abs(abs(p["amount"]) - inv["amount"]) > TOLERANCE:
                continue
            if abs((p["txn_date"] - inv["invoice_date"]).days) > PAYMENT_MATCH_WINDOW_DAYS:
                continue
            used_payment_idx.add(idx)
            matched = True
            break
        if matched:
            continue  # fully settled — not outstanding

        age = (as_of - inv["invoice_date"]).days
        bucket = (
            "0-30" if age <= 30 else "31-60" if age <= 60 else "61-90" if age <= 90
            else "91-180" if age <= 180 else "181-365" if age <= 365 else ">365"
        )
        out.append(AgeingBucket(inv["party"], inv["invoice_no"], inv["amount"], age, bucket))
    return out
