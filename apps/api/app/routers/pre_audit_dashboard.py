from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, CurrentUser
from ..books_health import compute_books_health

router = APIRouter(prefix="/engagements/{engagement_id}/pre-audit", tags=["pre-audit"])


class ModuleStatus(BaseModel):
    module: str
    books: str    # 'GREEN' | 'AMBER' | 'RED' | 'NO_DATA'  — Section 51's control-tower style status
    exception_count: int
    material_exception_count: int


class PreAuditDashboardOut(BaseModel):
    data_coverage_pct: float
    required_data_missing: int
    books_health_score: float
    books_health_factors: list[str]
    module_status: list[ModuleStatus]
    critical_exception_count: int
    overall_status: str  # 'READY' | 'NOT_READY'
    blockers: list[str]


@router.get("", response_model=PreAuditDashboardOut)
async def get_pre_audit_dashboard(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        # Data coverage (reuses the same computation as the Data Centre
        # endpoint — kept as a lightweight inline query here rather than an
        # HTTP call to avoid a self-referential API dependency).
        required_total = await conn.fetchval(
            "select count(distinct dataset_type) from data_coverage where engagement_id=$1", engagement_id
        ) or 0
        uploaded_count = await conn.fetchval(
            "select count(distinct dataset_type) from data_coverage where engagement_id=$1 and status in ('UPLOADED','PARTIAL')",
            engagement_id,
        ) or 0
        coverage_pct = round(100 * uploaded_count / required_total, 1) if required_total else 0.0
        missing_count = await conn.fetchval(
            "select count(*) from data_coverage where engagement_id=$1 and status='NOT_UPLOADED'", engagement_id
        ) or 0

        # Books health
        suspense_count = await conn.fetchval(
            "select count(*) from account where engagement_id=$1 and is_suspense=true", engagement_id
        ) or 0
        tb_flag_count = await conn.fetchval(
            "select count(distinct account_id) from trial_balance_line where engagement_id=$1 and flag is not null", engagement_id
        ) or 0
        acct_counts = await conn.fetchrow(
            "select count(*) as total, count(*) filter (where mapped_by is null) as unmapped from account where engagement_id=$1",
            engagement_id,
        )
        je_counts = await conn.fetchrow(
            "select count(*) filter (where risk_level in ('HIGH','CRITICAL')) as hc, count(*) as total "
            "from journal where engagement_id=$1 and risk_level is not null", engagement_id,
        )
        health = compute_books_health(
            suspense_count, tb_flag_count, acct_counts["unmapped"] or 0, acct_counts["total"] or 0,
            je_counts["hc"] or 0, je_counts["total"] or 0,
        )

        # Module status — reuses the existing reconciliation_exception data
        # built in Phases 6/11, grouped into a Section 51 control-tower view.
        module_rows = await conn.fetch(
            """select
                 case
                   when r.recon_type like 'GST_%' then 'GST'
                   when r.recon_type = 'TDS_RECONCILIATION' then 'TDS'
                   when r.recon_type like 'PAYROLL_%' then 'Payroll Statutory'
                 end as module,
                 count(*) as exception_count,
                 count(*) filter (where e.risk_level in ('HIGH','CRITICAL')) as material_count
               from reconciliation_exception e join reconciliation_run r on r.id=e.run_id
               where r.engagement_id=$1
               group by 1""",
            engagement_id,
        )
        modules_seen = {r["module"]: r for r in module_rows if r["module"]}
        module_status = []
        for m in ("GST", "TDS", "Payroll Statutory"):
            if m in modules_seen:
                r = modules_seen[m]
                material = r["material_count"] or 0
                books = "RED" if material > 0 else ("AMBER" if r["exception_count"] > 0 else "GREEN")
                module_status.append(ModuleStatus(module=m, books=books, exception_count=r["exception_count"], material_exception_count=material))
            else:
                module_status.append(ModuleStatus(module=m, books="NO_DATA", exception_count=0, material_exception_count=0))

        critical_count = await conn.fetchval(
            "select count(*) from audit_exception where engagement_id=$1 and risk_level in ('HIGH','CRITICAL') and status not in ('CLOSED','WAIVED')",
            engagement_id,
        ) or 0

    blockers = []
    if missing_count > 0:
        blockers.append(f"{missing_count} required dataset(s) not yet uploaded")
    if critical_count > 0:
        blockers.append(f"{critical_count} unresolved HIGH/CRITICAL exception(s)")
    if health.score < 70:
        blockers.append(f"Books health score is {health.score}/100 — below the 70 threshold")

    overall = "READY" if not blockers else "NOT_READY"

    return PreAuditDashboardOut(
        data_coverage_pct=coverage_pct, required_data_missing=missing_count,
        books_health_score=health.score, books_health_factors=health.factors,
        module_status=module_status, critical_exception_count=critical_count,
        overall_status=overall, blockers=blockers,
    )
