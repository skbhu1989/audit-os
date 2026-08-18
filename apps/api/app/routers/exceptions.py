from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, require_roles, CurrentUser
from ..ap_ar_reconciliation import compute_ageing, detect_duplicate_invoices
from .ap_ar import _load_bank_payments
from ..challan_mapping import match_challans_to_bank

router = APIRouter(prefix="/engagements/{engagement_id}/exceptions", tags=["exceptions"])
WRITE_ROLES = ("FIRM_ADMIN", "PARTNER", "MANAGER", "SENIOR")

VALID_STATUSES = (
    "OPEN", "ASSIGNED", "IN_PROGRESS", "CLIENT_RESPONSE", "UNDER_REVIEW",
    "ACCEPTED", "ADJUSTED", "NOTED", "CLOSED", "WAIVED", "CARRIED_FORWARD",
)


class ExceptionOut(BaseModel):
    id: UUID
    module: str | None
    period: str | None
    amount: float | None
    difference: float | None
    reason: str | None
    risk_level: str
    status: str
    owner_id: UUID | None
    due_date: str | None
    resolution: str | None


@router.get("", response_model=list[ExceptionOut])
async def list_exceptions(
    engagement_id: UUID,
    module: str | None = Query(None),
    risk_level: str | None = Query(None),
    exc_status: str | None = Query(None, alias="status"),
    owner_id: UUID | None = Query(None),
    user: CurrentUser = Depends(get_current_user),
):
    conditions = ["engagement_id = $1"]
    params: list = [engagement_id]
    if module:
        params.append(module); conditions.append(f"module = ${len(params)}")
    if risk_level:
        params.append(risk_level); conditions.append(f"risk_level = ${len(params)}")
    if exc_status:
        params.append(exc_status); conditions.append(f"status = ${len(params)}")
    if owner_id:
        params.append(owner_id); conditions.append(f"owner_id = ${len(params)}")

    async with tenant_conn(user.firm_id) as conn:
        rows = await conn.fetch(
            f"""select id, module, period, amount, difference, reason, risk_level, status, owner_id, due_date, resolution
                from audit_exception where {' and '.join(conditions)}
                order by case risk_level when 'CRITICAL' then 1 when 'HIGH' then 2 when 'MEDIUM' then 3 when 'MODERATE' then 4 else 5 end,
                         created_at""",
            *params,
        )
    return [
        ExceptionOut(
            id=r["id"], module=r["module"], period=r["period"],
            amount=float(r["amount"]) if r["amount"] is not None else None,
            difference=float(r["difference"]) if r["difference"] is not None else None,
            reason=r["reason"], risk_level=r["risk_level"], status=r["status"],
            owner_id=r["owner_id"], due_date=str(r["due_date"]) if r["due_date"] else None, resolution=r["resolution"],
        ) for r in rows
    ]


class UpdateExceptionRequest(BaseModel):
    status: str | None = None
    owner_id: UUID | None = None
    due_date: str | None = None
    resolution: str | None = None


@router.patch("/{exception_id}", status_code=204)
async def update_exception(
    engagement_id: UUID, exception_id: UUID, body: UpdateExceptionRequest,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    if body.status and body.status not in VALID_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"status must be one of: {', '.join(VALID_STATUSES)}")
    async with tenant_conn(user.firm_id) as conn:
        existing = await conn.fetchrow("select id from audit_exception where id=$1 and engagement_id=$2", exception_id, engagement_id)
        if not existing:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Exception not found")
        updates = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
        if not updates:
            return
        set_clause = ", ".join(f"{k}=${i+2}" for i, k in enumerate(updates))
        await conn.execute(f"update audit_exception set {set_clause}, updated_at=now() where id=$1", exception_id, *updates.values())


class SyncResult(BaseModel):
    exceptions_created: int
    sources: dict[str, int]


@router.post("/sync", response_model=SyncResult)
async def sync_exceptions(engagement_id: UUID, user: CurrentUser = Depends(require_roles(*WRITE_ROLES))):
    """AP ageing (>180 days), duplicate invoices, and challan mapping
    (UNMAPPED/MISMATCHED) are computed live by their own read-only
    endpoints but don't automatically create audit_exception rows the way
    GST/TDS/Payroll reconciliation does. This endpoint closes that gap —
    Section 60 calls for ONE central exception engine, not a hub that only
    some modules report into."""
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select reporting_date from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        created = {"ap_ageing": 0, "ap_duplicates": 0, "ar_ageing": 0, "challan_mapping": 0}

        async def _exists(module, reason):
            return await conn.fetchval(
                "select 1 from audit_exception where engagement_id=$1 and module=$2 and reason=$3 and status not in ('CLOSED','WAIVED')",
                engagement_id, module, reason,
            )

        # AP ageing
        ap_invoices = await conn.fetch(
            """select i.invoice_no, i.invoice_date, i.total_value as amount, coalesce(v.name,c.name) as party
               from invoice i left join vendor v on v.id=i.vendor_id left join customer c on c.id=i.customer_id
               where i.engagement_id=$1 and i.direction='PURCHASE'""", engagement_id)
        ap_dicts = [{"invoice_no": r["invoice_no"], "invoice_date": r["invoice_date"], "amount": float(r["amount"]), "party": r["party"]} for r in ap_invoices]
        for a in compute_ageing(ap_dicts, await _load_bank_payments(conn, engagement_id, "PURCHASE"), eng["reporting_date"]):
            if a.bucket in (">365", "181-365"):
                reason = f"AP balance outstanding {a.age_days} days: {a.party}, invoice {a.invoice_no}"
                if not await _exists("AP", reason):
                    await conn.execute(
                        """insert into audit_exception (engagement_id, source_type, module, fs_area,
                                                          amount, reason, risk_level, recommended_action, status)
                           values ($1,'ANALYTICS','AP','AP',$2,$3,$4,$5,'OPEN')""",
                        engagement_id, a.outstanding, reason, "HIGH" if a.bucket == ">365" else "MEDIUM",
                        "Confirm balance with vendor and investigate why it remains unpaid",
                    )
                    created["ap_ageing"] += 1

        # AP duplicate invoices
        dups = detect_duplicate_invoices(ap_dicts)
        for d in dups:
            reason = f"Possible duplicate invoice: {d.invoice_a} vs {d.invoice_b} ({d.party}, Rs {d.amount:,.0f})"
            if not await _exists("AP", reason):
                await conn.execute(
                    """insert into audit_exception (engagement_id, source_type, module, fs_area, amount,
                                                       reason, risk_level, recommended_action, status)
                       values ($1,'ANALYTICS','AP','AP',$2,$3,$4,$5,'OPEN')""",
                    engagement_id, d.amount, reason, d.confidence,
                    "Confirm with vendor whether both invoices are genuine; check for duplicate payment risk",
                )
                created["ap_duplicates"] += 1

        # AR ageing
        ar_invoices = await conn.fetch(
            """select i.invoice_no, i.invoice_date, i.total_value as amount, coalesce(v.name,c.name) as party
               from invoice i left join vendor v on v.id=i.vendor_id left join customer c on c.id=i.customer_id
               where i.engagement_id=$1 and i.direction='SALES'""", engagement_id)
        ar_dicts = [{"invoice_no": r["invoice_no"], "invoice_date": r["invoice_date"], "amount": float(r["amount"]), "party": r["party"]} for r in ar_invoices]
        for a in compute_ageing(ar_dicts, await _load_bank_payments(conn, engagement_id, "SALES"), eng["reporting_date"]):
            if a.bucket in (">365", "181-365"):
                reason = f"AR balance outstanding {a.age_days} days: {a.party}, invoice {a.invoice_no}"
                if not await _exists("AR", reason):
                    await conn.execute(
                        """insert into audit_exception (engagement_id, source_type, module, fs_area,
                                                           amount, reason, risk_level, recommended_action, status)
                           values ($1,'ANALYTICS','AR','AR',$2,$3,$4,$5,'OPEN')""",
                        engagement_id, a.outstanding, reason, "HIGH" if a.bucket == ">365" else "MEDIUM",
                        "Assess recoverability and ECL provisioning adequacy; obtain balance confirmation",
                    )
                    created["ar_ageing"] += 1

        # Challan mapping (GST/TDS/PF/ESI/PT)
        bank_txns = await conn.fetch("select id, txn_date, amount from bank_transaction where engagement_id=$1", engagement_id)
        b_dicts = [{"id": str(b["id"]), "txn_date": b["txn_date"], "amount": float(b["amount"])} for b in bank_txns]
        for scheme in ("GST", "TDS", "PF", "ESI", "PT"):
            challans = await conn.fetch(
                "select id, challan_date, amount, tax_head from challan where engagement_id=$1 and statutory_type=$2",
                engagement_id, scheme,
            )
            if not challans:
                continue
            c_dicts = [{"id": str(c["id"]), "challan_date": c["challan_date"], "amount": float(c["amount"])} for c in challans]
            for m in match_challans_to_bank(c_dicts, b_dicts):
                if m.status == "MATCHED":
                    continue
                reason = f"{scheme} challan payment {m.status.lower()} against bank statement (Rs {m.amount:,.0f})"
                if not await _exists(scheme, reason):
                    await conn.execute(
                        """insert into audit_exception (engagement_id, source_type, compliance_type, module, fs_area,
                                                           amount, reason, risk_level, recommended_action, status)
                           values ($1,'ANALYTICS',$2,$3,$4,$5,$6,$7,$8,'OPEN')""",
                        engagement_id, scheme, scheme, scheme,
                        m.amount, reason, "HIGH" if m.status == "UNMAPPED" else "MEDIUM",
                        "Confirm whether the challan was actually paid and locate the corresponding bank entry",
                    )
                    created["challan_mapping"] += 1

    return SyncResult(exceptions_created=sum(created.values()), sources=created)
