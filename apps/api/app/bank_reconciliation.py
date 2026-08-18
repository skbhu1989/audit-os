"""
Bank Reconciliation (Section 54): BANK STATEMENT ↔ BANK LEDGER.

The "bank ledger" side is the journal_line entries posted to whichever
account(s) are mapped to note_ref = 'Cash and Bank Balances' — the GL's
record of cash movement, as distinct from the externally-sourced bank
statement (bank_transaction). Reuses the same matching shape as
challan_mapping.py, per Section 124.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date

TOLERANCE = 1.0
DATE_WINDOW_DAYS = 3


@dataclass
class BankReconMatch:
    bank_txn_id: str
    status: str  # 'MATCHED' | 'UNPRESENTED_IN_BOOKS' | 'UNCREDITED_IN_STATEMENT' (see note)
    ledger_entry_id: str | None
    bank_amount: float
    ledger_amount: float | None


def reconcile_bank(bank_txns: list[dict], ledger_entries: list[dict]) -> list[BankReconMatch]:
    """bank_txns: [{'id','txn_date','amount'}] (signed: + = credit/money in, - = debit/money out)
    ledger_entries: [{'id','posted_date','amount'}] (same sign convention, derived by caller
    from journal_line.debit - journal_line.credit on the bank account)."""
    used_ledger_ids = set()
    results = []
    for b in bank_txns:
        candidates = [
            l for l in ledger_entries
            if l["id"] not in used_ledger_ids
            and abs(l["amount"] - b["amount"]) <= TOLERANCE
            and abs((l["posted_date"] - b["txn_date"]).days) <= DATE_WINDOW_DAYS
        ]
        if candidates:
            best = min(candidates, key=lambda l: abs((l["posted_date"] - b["txn_date"]).days))
            used_ledger_ids.add(best["id"])
            results.append(BankReconMatch(b["id"], "MATCHED", best["id"], b["amount"], best["amount"]))
        else:
            # In the bank statement but not (yet, or ever) in the books —
            # Section 54's "unpresented cheque" / "uncredited receipt" /
            # "bank charges not yet booked" bucket. This system can't yet
            # distinguish which of those it is (needs description-based
            # classification, not built) — flagged generically as a books-
            # side gap rather than guessing the specific cause.
            results.append(BankReconMatch(b["id"], "MISSING_IN_BOOKS", None, b["amount"], None))

    for l in ledger_entries:
        if l["id"] not in used_ledger_ids:
            results.append(BankReconMatch(None, "MISSING_IN_BANK_STATEMENT", l["id"], None, l["amount"]))

    return results
