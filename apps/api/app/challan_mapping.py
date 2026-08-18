"""
GST Challan Mapping (Section 24) and TDS Challan Mapping (Section 26) share
identical structure — a challan payment needs confirmation against an actual
bank debit. Built once, reused for both statutory types (and PF/ESI/PT),
per Section 124's "do not build duplicate logic if it can be generalized."
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date

TOLERANCE = 1.0
DATE_WINDOW_DAYS = 5  # a challan payment should show up in the bank statement within a few days


@dataclass
class ChallanMatch:
    challan_id: str
    status: str  # 'MAPPED' | 'UNMAPPED' | 'MISMATCHED'
    bank_txn_id: str | None
    amount: float
    matched_amount: float | None
    date_diff_days: int | None


def match_challans_to_bank(
    challans: list[dict], bank_txns: list[dict]
) -> list[ChallanMatch]:
    """challans: [{'id','challan_date','amount'}], bank_txns: [{'id','txn_date','amount'}]
    (bank amount expected negative for a payment out, per the schema convention)."""
    used_bank_ids = set()
    results = []
    for c in challans:
        candidates = [
            b for b in bank_txns
            if b["id"] not in used_bank_ids
            and abs(abs(b["amount"]) - c["amount"]) <= TOLERANCE
            and abs((b["txn_date"] - c["challan_date"]).days) <= DATE_WINDOW_DAYS
        ]
        if candidates:
            best = min(candidates, key=lambda b: abs((b["txn_date"] - c["challan_date"]).days))
            used_bank_ids.add(best["id"])
            results.append(ChallanMatch(
                challan_id=c["id"], status="MAPPED", bank_txn_id=best["id"],
                amount=c["amount"], matched_amount=abs(best["amount"]),
                date_diff_days=(best["txn_date"] - c["challan_date"]).days,
            ))
            continue

        # near-miss: same date window, amount doesn't match -> flag as MISMATCHED
        # rather than silently UNMAPPED, since it's likely the same payment
        # with a data entry error, not a genuinely missing one.
        near = [
            b for b in bank_txns
            if b["id"] not in used_bank_ids
            and abs((b["txn_date"] - c["challan_date"]).days) <= DATE_WINDOW_DAYS
        ]
        if near:
            best = min(near, key=lambda b: abs((b["txn_date"] - c["challan_date"]).days))
            used_bank_ids.add(best["id"])  # a bank txn can only be "the near-miss candidate" for one challan
            results.append(ChallanMatch(
                challan_id=c["id"], status="MISMATCHED", bank_txn_id=best["id"],
                amount=c["amount"], matched_amount=abs(best["amount"]),
                date_diff_days=(best["txn_date"] - c["challan_date"]).days,
            ))
            continue

        results.append(ChallanMatch(
            challan_id=c["id"], status="UNMAPPED", bank_txn_id=None,
            amount=c["amount"], matched_amount=None, date_diff_days=None,
        ))
    return results
