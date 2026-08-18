from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, CurrentUser
from ..challan_mapping import match_challans_to_bank
from ..bank_reconciliation import reconcile_bank

router = APIRouter(prefix="/engagements/{engagement_id}", tags=["bank-and-challan"])


class ChallanMappingOut(BaseModel):
    challan_id: UUID
    statutory_type: str
    tax_head: str | None
    status: str
    amount: float
    matched_amount: float | None
    date_diff_days: int | None


@router.get("/challan-mapping", response_model=list[ChallanMappingOut])
async def get_challan_mapping(
    engagement_id: UUID, statutory_type: str = Query(..., pattern="^(GST|TDS|PF|ESI|PT)$"),
    user: CurrentUser = Depends(get_current_user),
):
    """Computed live on every call rather than persisted — this is a
    read-heavy confirmation check (Section 24/26), not something that needs
    a full reconciliation_run/exception audit trail the way GST/TDS
    substantive reconciliation does. If that changes (e.g. an auditor wants
    to formally accept a mapping), promote this to the same
    reconciliation_run pattern used elsewhere."""
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        challans = await conn.fetch(
            "select id, challan_date, amount, tax_head from challan where engagement_id=$1 and statutory_type=$2",
            engagement_id, statutory_type,
        )
        if not challans:
            return []
        bank_txns = await conn.fetch(
            "select id, txn_date, amount from bank_transaction where engagement_id=$1", engagement_id
        )

        c_dicts = [{"id": str(c["id"]), "challan_date": c["challan_date"], "amount": float(c["amount"])} for c in challans]
        b_dicts = [{"id": str(b["id"]), "txn_date": b["txn_date"], "amount": float(b["amount"])} for b in bank_txns]
        results = match_challans_to_bank(c_dicts, b_dicts)

        by_id = {str(c["id"]): c for c in challans}
        out = []
        for r in results:
            c = by_id[r.challan_id]
            out.append(ChallanMappingOut(
                challan_id=c["id"], statutory_type=statutory_type, tax_head=c["tax_head"],
                status=r.status, amount=r.amount, matched_amount=r.matched_amount, date_diff_days=r.date_diff_days,
            ))
    return out


class BankReconOut(BaseModel):
    status: str
    bank_txn_id: UUID | None
    ledger_entry_id: UUID | None
    bank_amount: float | None
    ledger_amount: float | None
    description: str | None


@router.get("/bank-reconciliation", response_model=list[BankReconOut])
async def get_bank_reconciliation(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        bank_rows = await conn.fetch(
            "select id, txn_date, amount, description from bank_transaction where engagement_id=$1", engagement_id
        )
        # "Ledger" side: journal_line entries on any account mapped to
        # 'Cash and Bank Balances', signed the same way as bank_transaction
        # (debit on the bank account = money in = positive; credit = money out).
        ledger_rows = await conn.fetch(
            """select jl.id, j.posted_date, (jl.debit - jl.credit) as amount
               from journal_line jl join journal j on j.id = jl.journal_id
               join account a on a.id = jl.account_id
               where j.engagement_id = $1 and a.note_ref = 'Cash and Bank Balances'""",
            engagement_id,
        )
        if not bank_rows and not ledger_rows:
            return []

        b_dicts = [{"id": str(b["id"]), "txn_date": b["txn_date"], "amount": float(b["amount"])} for b in bank_rows]
        l_dicts = [{"id": str(l["id"]), "posted_date": l["posted_date"], "amount": float(l["amount"])} for l in ledger_rows]
        results = reconcile_bank(b_dicts, l_dicts)

        desc_by_id = {str(b["id"]): b["description"] for b in bank_rows}
        out = [
            BankReconOut(
                status=r.status, bank_txn_id=r.bank_txn_id, ledger_entry_id=r.ledger_entry_id,
                bank_amount=r.bank_amount, ledger_amount=r.ledger_amount,
                description=desc_by_id.get(r.bank_txn_id),
            ) for r in results
        ]
    return out
