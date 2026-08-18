from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, CurrentUser
from ..control_tower import build_row

router = APIRouter(prefix="/engagements/{engagement_id}/control-tower", tags=["control-tower"])


class ControlTowerRowOut(BaseModel):
    row: str
    books: bool | None
    return_: bool | None
    payment: bool | None
    document: bool | None
    status: str
    exception_count: int
    material_count: int


class ControlTowerOut(BaseModel):
    rows: list[ControlTowerRowOut]
    overall_status: str  # worst of all rows


@router.get("", response_model=ControlTowerOut)
async def get_control_tower(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        async def exc_counts(recon_type_pattern: str) -> tuple[int, int]:
            row = await conn.fetchrow(
                """select count(*) as total, count(*) filter (where risk_level in ('HIGH','CRITICAL')) as material
                   from reconciliation_exception e join reconciliation_run r on r.id=e.run_id
                   where r.engagement_id=$1 and r.recon_type like $2""",
                engagement_id, recon_type_pattern,
            )
            return row["total"] or 0, row["material"] or 0

        # Revenue: books presence = sales register (invoice direction=SALES);
        # "return" = GSTR-1 (revenue's statutory counterpart); payment = N/A
        # (revenue isn't "paid"); document = e-invoice/IRN present on any invoice.
        revenue_books = await conn.fetchval("select count(*) from invoice where engagement_id=$1 and direction='SALES'", engagement_id) or 0
        revenue_return = await conn.fetchval("select count(*) from gst_transaction where engagement_id=$1 and source='GSTR1'", engagement_id) or 0
        revenue_doc = await conn.fetchval("select count(*) from invoice where engagement_id=$1 and direction='SALES' and irn is not null", engagement_id) or 0
        revenue_exc, revenue_mat = await exc_counts("GST_BOOKS_VS_GSTR1")

        gst_books = revenue_books  # GST books-side is the same sales/purchase data
        gst_return = await conn.fetchval("select count(*) from gst_transaction where engagement_id=$1 and source in ('GSTR1','GSTR3B')", engagement_id) or 0
        gst_payment = await conn.fetchval("select count(*) from challan where engagement_id=$1 and statutory_type='GST'", engagement_id) or 0
        gst_doc = await conn.fetchval("select count(*) from document where engagement_id=$1 and category='RETURN_FILING'", engagement_id) or 0
        gst_exc, gst_mat = await exc_counts("GST_%")

        tds_books = await conn.fetchval("select count(*) from tds_transaction where engagement_id=$1 and source='LEDGER'", engagement_id) or 0
        tds_return = await conn.fetchval("select count(*) from tds_transaction where engagement_id=$1 and source='RETURN'", engagement_id) or 0
        tds_payment = await conn.fetchval("select count(*) from challan where engagement_id=$1 and statutory_type='TDS'", engagement_id) or 0
        tds_doc = await conn.fetchval("select count(*) from document where engagement_id=$1 and category='CHALLAN'", engagement_id) or 0
        tds_exc, tds_mat = await exc_counts("TDS_RECONCILIATION")

        payroll_books = await conn.fetchval("select count(*) from payroll_line where engagement_id=$1", engagement_id) or 0
        payroll_payment = await conn.fetchval("select count(*) from challan where engagement_id=$1 and statutory_type in ('PF','ESI','PT')", engagement_id) or 0
        payroll_exc, payroll_mat = await exc_counts("PAYROLL_%")

        bank_books = await conn.fetchval("select count(*) from bank_transaction where engagement_id=$1", engagement_id) or 0
        bank_ledger = await conn.fetchval(
            """select count(*) from journal_line jl join account a on a.id=jl.account_id join journal j on j.id=jl.journal_id
               where j.engagement_id=$1 and a.note_ref='Cash and Bank Balances'""", engagement_id) or 0
        bank_exc = await conn.fetchval("select count(*) from audit_exception where engagement_id=$1 and module='BANK'", engagement_id) or 0
        bank_mat = await conn.fetchval(
            "select count(*) from audit_exception where engagement_id=$1 and module='BANK' and risk_level in ('HIGH','CRITICAL')",
            engagement_id) or 0

        ap_books = await conn.fetchval("select count(*) from invoice where engagement_id=$1 and direction='PURCHASE'", engagement_id) or 0
        ap_exc = await conn.fetchval("select count(*) from audit_exception where engagement_id=$1 and module='AP'", engagement_id) or 0
        ap_mat = await conn.fetchval("select count(*) from audit_exception where engagement_id=$1 and module='AP' and risk_level in ('HIGH','CRITICAL')", engagement_id) or 0

        ar_books = await conn.fetchval("select count(*) from invoice where engagement_id=$1 and direction='SALES'", engagement_id) or 0
        ar_exc = await conn.fetchval("select count(*) from audit_exception where engagement_id=$1 and module='AR'", engagement_id) or 0
        ar_mat = await conn.fetchval("select count(*) from audit_exception where engagement_id=$1 and module='AR' and risk_level in ('HIGH','CRITICAL')", engagement_id) or 0

    rows_data = [
        ("Revenue", revenue_books > 0, revenue_return > 0, None, revenue_doc > 0, revenue_exc, revenue_mat),
        ("GST", gst_books > 0, gst_return > 0, gst_payment > 0, gst_doc > 0, gst_exc, gst_mat),
        ("TDS", tds_books > 0, tds_return > 0, tds_payment > 0, tds_doc > 0, tds_exc, tds_mat),
        ("Payroll (PF/ESI/PT)", payroll_books > 0, None, payroll_payment > 0, None, payroll_exc, payroll_mat),
        ("Bank", bank_books > 0, None, bank_ledger > 0, bank_books > 0, bank_exc, bank_mat),
        ("AP", ap_books > 0, None, None, None, ap_exc, ap_mat),
        ("AR", ar_books > 0, None, None, None, ar_exc, ar_mat),
    ]

    out_rows = []
    for name, books, ret, pay, doc, exc, mat in rows_data:
        cell = build_row(books, ret, pay, doc, exc, mat)
        out_rows.append(ControlTowerRowOut(
            row=name, books=cell.books, return_=cell.return_, payment=cell.payment, document=cell.document,
            status=cell.status, exception_count=exc, material_count=mat,
        ))

    status_rank = {"RED": 0, "AMBER": 1, "NO_DATA": 2, "GREEN": 3}
    overall = min((r.status for r in out_rows), key=lambda s: status_rank[s])

    return ControlTowerOut(rows=out_rows, overall_status=overall)
