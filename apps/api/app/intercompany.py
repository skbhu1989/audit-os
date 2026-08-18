"""
Intercompany Reconciliation (Section 33).

Scoping note (see migration 025's comment): true cross-entity ("Entity A ↔
Entity B") reconciliation needs group-structure tracking this system
doesn't have. What's built: THIS entity's own intercompany ledger vs an
uploaded counterparty confirmation — the same internal-record-vs-external-
confirmation shape as bank reconciliation (Section 54), applied here.
"""
from __future__ import annotations
from dataclasses import dataclass

TOLERANCE = 1.0
DATE_WINDOW_DAYS = 15  # intercompany postings are often a few days apart between entities' books


@dataclass
class IntercompanyMatch:
    counterparty_name: str
    status: str  # 'MATCHED' | 'MISSING_IN_BOOKS' | 'MISSING_IN_CONFIRMATION' | 'MISMATCHED'
    books_amount: float | None
    confirmation_amount: float | None
    difference: float | None
    likely_cause: str | None


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _classify_cause(books_txn: dict, conf_txn: dict) -> str:
    days_apart = abs((conf_txn["transaction_date"] - books_txn["transaction_date"]).days)
    if days_apart > 5:
        return f"Same counterparty and similar amount but {days_apart} days apart — likely a timing/period-end cut-off difference"
    return "Same counterparty and close in time but the amount differs — likely a recording error on one side, or a genuine FX/rounding difference if cross-border"


def reconcile_intercompany(books: list[dict], confirmation: list[dict]) -> list[IntercompanyMatch]:
    """books/confirmation: [{'counterparty_name','transaction_date','amount','reference_no'}]."""
    used_conf_idx = set()
    results = []

    for b in books:
        candidates = [
            (j, c) for j, c in enumerate(confirmation)
            if j not in used_conf_idx
            and _norm(c["counterparty_name"]) == _norm(b["counterparty_name"])
            and abs(c["amount"] - b["amount"]) <= TOLERANCE
            and abs((c["transaction_date"] - b["transaction_date"]).days) <= DATE_WINDOW_DAYS
        ]
        if candidates:
            j, c = candidates[0]
            used_conf_idx.add(j)
            results.append(IntercompanyMatch(b["counterparty_name"], "MATCHED", b["amount"], c["amount"], 0.0, None))
            continue

        near = [
            (j, c) for j, c in enumerate(confirmation)
            if j not in used_conf_idx
            and _norm(c["counterparty_name"]) == _norm(b["counterparty_name"])
            and abs((c["transaction_date"] - b["transaction_date"]).days) <= DATE_WINDOW_DAYS
        ]
        if near:
            j, c = near[0]
            used_conf_idx.add(j)
            diff = round(b["amount"] - c["amount"], 2)
            results.append(IntercompanyMatch(
                b["counterparty_name"], "MISMATCHED", b["amount"], c["amount"], diff, _classify_cause(b, c),
            ))
            continue

        results.append(IntercompanyMatch(
            b["counterparty_name"], "MISSING_IN_CONFIRMATION", b["amount"], None, b["amount"],
            "Recorded in books but not confirmed by the counterparty",
        ))

    for j, c in enumerate(confirmation):
        if j not in used_conf_idx:
            results.append(IntercompanyMatch(
                c["counterparty_name"], "MISSING_IN_BOOKS", None, c["amount"], -c["amount"],
                "Confirmed by the counterparty but not found in this entity's books",
            ))

    return results


@dataclass
class CounterpartySummary:
    counterparty_name: str
    net_books_position: float  # positive = counterparty owes us
    transaction_count: int


def summarize_by_counterparty(books: list[dict]) -> list[CounterpartySummary]:
    totals: dict[str, list] = {}
    for b in books:
        key = b["counterparty_name"]
        totals.setdefault(key, [0.0, 0])
        totals[key][0] += b["amount"]
        totals[key][1] += 1
    return [CounterpartySummary(name, round(v[0], 2), v[1]) for name, v in totals.items()]
