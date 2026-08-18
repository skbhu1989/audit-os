from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, require_roles, CurrentUser
from ..month_end_close import DEFAULT_CLOSE_TASKS, derive_bank_status, derive_recon_status, derive_ap_ar_status
from ..bank_reconciliation import reconcile_bank
from ..ap_ar_reconciliation import compute_ageing, detect_duplicate_invoices
from .ap_ar import _load_bank_payments as _load_bank_payments_for_close

router = APIRouter(prefix="/engagements/{engagement_id}/month-end-close", tags=["month-end-close"])
WRITE_ROLES = ("FIRM_ADMIN", "PARTNER", "MANAGER", "SENIOR")


class InitResult(BaseModel):
    tasks_seeded: int
    tasks_already_existed: int


@router.post("/init", response_model=InitResult)
async def init_close(engagement_id: UUID, period: str, user: CurrentUser = Depends(require_roles(*WRITE_ROLES))):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")
        seeded, existed = 0, 0
        for category, task_name, is_system in DEFAULT_CLOSE_TASKS:
            existing = await conn.fetchrow(
                "select id from month_end_close_task where engagement_id=$1 and period=$2 and category=$3 and task_name=$4",
                engagement_id, period, category, task_name,
            )
            if existing:
                existed += 1
                continue
            await conn.execute(
                """insert into month_end_close_task (engagement_id, period, category, task_name, is_system_computed)
                   values ($1,$2,$3,$4,$5)""",
                engagement_id, period, category, task_name, is_system,
            )
            seeded += 1
    return InitResult(tasks_seeded=seeded, tasks_already_existed=existed)


class CloseTaskOut(BaseModel):
    id: UUID
    category: str
    task_name: str
    is_system_computed: bool
    status: str
    owner_id: UUID | None
    due_date: str | None
    evidence_note: str | None


@router.get("", response_model=list[CloseTaskOut])
async def get_close_checklist(engagement_id: UUID, period: str, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        tasks = await conn.fetch(
            "select * from month_end_close_task where engagement_id=$1 and period=$2 order by category", engagement_id, period
        )
        if not tasks:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No close checklist found for this period — call POST .../init first")

        # Live-compute status for system-backed tasks rather than trusting a
        # possibly-stale stored value — these always reflect the current
        # state of the underlying reconciliation data.
        bank_recon_items = []
        bank_rows = await conn.fetch("select txn_date, amount from bank_transaction where engagement_id=$1", engagement_id)
        ledger_rows = await conn.fetch(
            """select jl.id, j.posted_date, (jl.debit - jl.credit) as amount
               from journal_line jl join journal j on j.id=jl.journal_id join account a on a.id=jl.account_id
               where j.engagement_id=$1 and a.note_ref='Cash and Bank Balances'""", engagement_id,
        )
        if bank_rows or ledger_rows:
            b = [{"id": str(i), "txn_date": r["txn_date"], "amount": float(r["amount"])} for i, r in enumerate(bank_rows)]
            l = [{"id": str(r["id"]), "posted_date": r["posted_date"], "amount": float(r["amount"])} for r in ledger_rows]
            bank_recon_items = [{"status": m.status} for m in reconcile_bank(b, l)]

        gst_run = await conn.fetchval("select count(*) from reconciliation_run where engagement_id=$1 and recon_type like 'GST_%'", engagement_id)
        gst_exceptions = await conn.fetch(
            """select e.risk_level from reconciliation_exception e join reconciliation_run r on r.id=e.run_id
               where r.engagement_id=$1 and r.recon_type like 'GST_%'""", engagement_id)

        tds_run = await conn.fetchval("select count(*) from reconciliation_run where engagement_id=$1 and recon_type='TDS_RECONCILIATION'", engagement_id)
        tds_exceptions = await conn.fetch(
            """select e.risk_level from reconciliation_exception e join reconciliation_run r on r.id=e.run_id
               where r.engagement_id=$1 and r.recon_type='TDS_RECONCILIATION'""", engagement_id)

        payroll_run = await conn.fetchval("select count(*) from reconciliation_run where engagement_id=$1 and recon_type like 'PAYROLL_%'", engagement_id)
        payroll_exceptions = await conn.fetch(
            """select e.risk_level from reconciliation_exception e join reconciliation_run r on r.id=e.run_id
               where r.engagement_id=$1 and r.recon_type like 'PAYROLL_%'""", engagement_id)

        eng_row = await conn.fetchrow("select reporting_date from engagement where id=$1", engagement_id)
        ap_invoices = await conn.fetch(
            """select i.invoice_no, i.invoice_date, i.total_value as amount, coalesce(v.name,c.name) as party
               from invoice i left join vendor v on v.id=i.vendor_id left join customer c on c.id=i.customer_id
               where i.engagement_id=$1 and i.direction='PURCHASE'""", engagement_id)
        ap_dicts = [{"invoice_no": r["invoice_no"], "invoice_date": r["invoice_date"], "amount": float(r["amount"]), "party": r["party"]} for r in ap_invoices]
        ap_dups = detect_duplicate_invoices(ap_dicts)

        ar_invoices = await conn.fetch(
            """select i.invoice_no, i.invoice_date, i.total_value as amount, coalesce(v.name,c.name) as party
               from invoice i left join vendor v on v.id=i.vendor_id left join customer c on c.id=i.customer_id
               where i.engagement_id=$1 and i.direction='SALES'""", engagement_id)
        ar_dicts = [{"invoice_no": r["invoice_no"], "invoice_date": r["invoice_date"], "amount": float(r["amount"]), "party": r["party"]} for r in ar_invoices]

        # Bank-payment matching for AP/AR status must use the SAME logic as
        # the dedicated /ap/ageing and /ar/ageing endpoints — an earlier
        # draft of this query skipped payment matching entirely ("omitted
        # for brevity"), which meant this checklist showed 3 AP balances
        # outstanding while the dedicated ageing endpoint correctly showed
        # only 1 (the other 2 had real matching bank payments). Two parts
        # of the same system reporting different numbers for the same fact
        # is exactly the kind of bug this whole build has been checking
        # for — fixed by reusing the identical vendor/customer-description
        # matching helper both endpoints now share.
        ap_payments = await _load_bank_payments_for_close(conn, engagement_id, "PURCHASE")
        ar_receipts = await _load_bank_payments_for_close(conn, engagement_id, "SALES")
        ap_ageing = compute_ageing(ap_dicts, ap_payments, eng_row["reporting_date"])
        ar_ageing = compute_ageing(ar_dicts, ar_receipts, eng_row["reporting_date"])

        computed = {
            "Bank": derive_bank_status(bank_recon_items),
            "GST": derive_recon_status([dict(e) for e in gst_exceptions], (gst_run or 0) > 0),
            "TDS": derive_recon_status([dict(e) for e in tds_exceptions], (tds_run or 0) > 0),
            "Payroll": derive_recon_status([dict(e) for e in payroll_exceptions], (payroll_run or 0) > 0),
            "AP": derive_ap_ar_status([{"bucket": a.bucket} for a in ap_ageing], len(ap_dups)),
            "AR": derive_ap_ar_status([{"bucket": a.bucket} for a in ar_ageing]),
        }

    out = []
    for t in tasks:
        if t["is_system_computed"] and t["category"] in computed:
            c = computed[t["category"]]
            out.append(CloseTaskOut(
                id=t["id"], category=t["category"], task_name=t["task_name"], is_system_computed=True,
                status=c.status, owner_id=t["owner_id"], due_date=str(t["due_date"]) if t["due_date"] else None,
                evidence_note=c.evidence_note,
            ))
        else:
            out.append(CloseTaskOut(
                id=t["id"], category=t["category"], task_name=t["task_name"], is_system_computed=False,
                status=t["status"], owner_id=t["owner_id"], due_date=str(t["due_date"]) if t["due_date"] else None,
                evidence_note=t["evidence_note"],
            ))
    return out


class UpdateTaskRequest(BaseModel):
    status: str | None = None
    owner_id: UUID | None = None
    due_date: str | None = None
    evidence_note: str | None = None


@router.patch("/{task_id}", status_code=204)
async def update_close_task(
    engagement_id: UUID, task_id: UUID, body: UpdateTaskRequest, user: CurrentUser = Depends(require_roles(*WRITE_ROLES))
):
    async with tenant_conn(user.firm_id) as conn:
        task = await conn.fetchrow(
            "select is_system_computed from month_end_close_task where id=$1 and engagement_id=$2", task_id, engagement_id
        )
        if not task:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
        if task["is_system_computed"] and body.status:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "This task's status is system-computed from live reconciliation data and cannot be manually overridden — "
                "resolve the underlying exceptions instead.",
            )
        updates = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
        if not updates:
            return
        set_clause = ", ".join(f"{k}=${i+2}" for i, k in enumerate(updates))
        await conn.execute(
            f"update month_end_close_task set {set_clause}, updated_at=now() where id=$1",
            task_id, *updates.values(),
        )
