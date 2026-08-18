from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, CurrentUser
from ..intercompany import reconcile_intercompany, summarize_by_counterparty

router = APIRouter(prefix="/engagements/{engagement_id}/intercompany", tags=["intercompany"])


class IntercompanyMatchOut(BaseModel):
    counterparty_name: str
    status: str
    books_amount: float | None
    confirmation_amount: float | None
    difference: float | None
    likely_cause: str | None


class CounterpartySummaryOut(BaseModel):
    counterparty_name: str
    net_books_position: float
    transaction_count: int


class IntercompanyOut(BaseModel):
    matches: list[IntercompanyMatchOut]
    counterparty_summary: list[CounterpartySummaryOut]
    matched_count: int
    unresolved_count: int


@router.get("", response_model=IntercompanyOut)
async def get_intercompany(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        books_rows = await conn.fetch(
            "select counterparty_name, transaction_date, amount, reference_no from intercompany_transaction where engagement_id=$1 and source='BOOKS'",
            engagement_id,
        )
        conf_rows = await conn.fetch(
            "select counterparty_name, transaction_date, amount, reference_no from intercompany_transaction where engagement_id=$1 and source='CONFIRMATION'",
            engagement_id,
        )

    books = [dict(r) for r in books_rows]
    confirmation = [dict(r) for r in conf_rows]
    for r in books + confirmation:
        r["amount"] = float(r["amount"])

    matches = reconcile_intercompany(books, confirmation)
    summary = summarize_by_counterparty(books)

    return IntercompanyOut(
        matches=[IntercompanyMatchOut(**m.__dict__) for m in matches],
        counterparty_summary=[CounterpartySummaryOut(**s.__dict__) for s in summary],
        matched_count=sum(1 for m in matches if m.status == "MATCHED"),
        unresolved_count=sum(1 for m in matches if m.status != "MATCHED"),
    )
