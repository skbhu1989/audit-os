from uuid import UUID
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, CurrentUser
from ..ap_ar_reconciliation import detect_duplicate_invoices, compute_ageing

router = APIRouter(prefix="/engagements/{engagement_id}", tags=["ap-ar"])


async def _load_invoices(conn, engagement_id, direction):
    rows = await conn.fetch(
        """select i.invoice_no, i.invoice_date, i.total_value as amount,
                  coalesce(v.name, c.name) as party
           from invoice i left join vendor v on v.id = i.vendor_id
                           left join customer c on c.id = i.customer_id
           where i.engagement_id = $1 and i.direction = $2""",
        engagement_id, direction,
    )
    # asyncpg returns `numeric` columns as Decimal, not float — every other
    # loader in this router already casts explicitly (_load_bank_payments
    # does), but this one didn't, causing a Decimal/float mismatch the
    # moment compute_ageing does arithmetic across both. Caught by running
    # the endpoint, not by reading the type signatures.
    return [{"invoice_no": r["invoice_no"], "invoice_date": r["invoice_date"],
              "amount": float(r["amount"]), "party": r["party"]} for r in rows]


async def _load_bank_payments(conn, engagement_id, direction):
    """direction 'PURCHASE' -> payments out (negative bank amount);
    'SALES' -> receipts in (positive). We don't have a vendor/customer name
    on bank_transaction directly — it's inferred from the free-text
    description via simple substring matching against the vendor/customer
    master, which is a real limitation (stated in the README) since a
    payment described differently than the master name won't match."""
    sign_filter = "< 0" if direction == "PURCHASE" else "> 0"
    parties = await conn.fetch(
        "select name from vendor where engagement_id=$1" if direction == "PURCHASE"
        else "select name from customer where engagement_id=$1", engagement_id,
    )
    bank_rows = await conn.fetch(
        f"select txn_date, amount, description from bank_transaction where engagement_id=$1 and amount {sign_filter}",
        engagement_id,
    )
    out = []
    for b in bank_rows:
        desc = (b["description"] or "").lower()
        for p in parties:
            if p["name"].lower() in desc:
                out.append({"party": p["name"], "amount": float(b["amount"]), "txn_date": b["txn_date"]})
                break
    return out


class DuplicateInvoiceOut(BaseModel):
    invoice_a: str
    invoice_b: str
    party: str
    amount: float
    date_diff_days: int
    confidence: str


@router.get("/ap/duplicate-invoices", response_model=list[DuplicateInvoiceOut])
async def get_duplicate_ap_invoices(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")
        invoices = await _load_invoices(conn, engagement_id, "PURCHASE")
    return [DuplicateInvoiceOut(**d.__dict__) for d in detect_duplicate_invoices(invoices)]


class AgeingOut(BaseModel):
    party: str
    invoice_no: str
    outstanding: float
    age_days: int
    bucket: str


@router.get("/ap/ageing", response_model=list[AgeingOut])
async def get_ap_ageing(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select reporting_date from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")
        invoices = await _load_invoices(conn, engagement_id, "PURCHASE")
        payments = await _load_bank_payments(conn, engagement_id, "PURCHASE")
        result = compute_ageing(invoices, payments, eng["reporting_date"])
    return [AgeingOut(**a.__dict__) for a in result]


@router.get("/ar/ageing", response_model=list[AgeingOut])
async def get_ar_ageing(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select reporting_date from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")
        invoices = await _load_invoices(conn, engagement_id, "SALES")
        receipts = await _load_bank_payments(conn, engagement_id, "SALES")
        result = compute_ageing(invoices, receipts, eng["reporting_date"])
    return [AgeingOut(**a.__dict__) for a in result]
