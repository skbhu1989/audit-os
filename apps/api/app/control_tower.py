"""
Universal Reconciliation Control Tower (Section 51) — the signature
dashboard: one matrix showing, per FS area, whether Books/Return/Payment/
Document data exists and an overall GREEN/AMBER/RED/NO_DATA status.

Same honesty discipline as every other dashboard in this build: a column
that doesn't apply to a given row (e.g. "Return" for Bank — there's no
statutory return for a bank account) is explicitly None (rendered as '—'),
never silently marked present or absent. NO_DATA status means the row's
books-side data doesn't exist yet, which is different from GREEN (data
exists and reconciles) or RED (data exists and has material exceptions) —
the same DATA GAP vs RECONCILIATION EXCEPTION distinction from Section 39.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class ControlTowerCell:
    books: bool | None
    return_: bool | None
    payment: bool | None
    document: bool | None
    status: str  # 'GREEN' | 'AMBER' | 'RED' | 'NO_DATA'


def compute_status(books_present: bool, exception_count: int, material_count: int) -> str:
    if not books_present:
        return "NO_DATA"
    if material_count > 0:
        return "RED"
    if exception_count > 0:
        return "AMBER"
    return "GREEN"


def build_row(
    books_present: bool, return_present: bool | None, payment_present: bool | None, document_present: bool | None,
    exception_count: int = 0, material_count: int = 0,
) -> ControlTowerCell:
    return ControlTowerCell(
        books=books_present, return_=return_present, payment=payment_present, document=document_present,
        status=compute_status(books_present, exception_count, material_count),
    )
