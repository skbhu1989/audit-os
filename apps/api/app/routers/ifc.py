from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, require_roles, CurrentUser
from ..ifc import (
    test_p2p_vendor_master, test_o2c_revenue_gst_completeness, test_r2r_journal_override,
    test_treasury_tb_balance_direction, test_tax_statutory_reconciliation,
)
from ..ai_assistant import build_duplicate_vendor_answer

router = APIRouter(prefix="/engagements/{engagement_id}/ifc", tags=["ifc"])
WRITE_ROLES = ("FIRM_ADMIN", "PARTNER", "MANAGER", "SENIOR")


class IfcRunResult(BaseModel):
    controls_tested: int
    effective_count: int
    exception_count: int


@router.post("/run-automated-tests", response_model=IfcRunResult)
async def run_automated_tests(engagement_id: UUID, user: CurrentUser = Depends(require_roles(*WRITE_ROLES))):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        vendors = await conn.fetch("select id, name from vendor where engagement_id=$1", engagement_id)
        dup_answer = build_duplicate_vendor_answer([dict(v) for v in vendors])
        dup_pairs = dup_answer.data_used.count(" vs ") if dup_answer else 0

        gst_books_vs_gstr1 = await conn.fetchval(
            """select count(*) from reconciliation_exception e join reconciliation_run r on r.id=e.run_id
               where r.engagement_id=$1 and r.recon_type='GST_BOOKS_VS_GSTR1'""", engagement_id) or 0

        je_counts = await conn.fetchrow(
            "select count(*) filter (where risk_level in ('HIGH','CRITICAL')) as hc, count(*) as total "
            "from journal where engagement_id=$1 and risk_level is not null", engagement_id)

        tb_flagged = await conn.fetchval(
            "select count(*) from trial_balance_line where engagement_id=$1 and flag is not null", engagement_id) or 0

        total_statutory = await conn.fetchval(
            """select count(*) from reconciliation_exception e join reconciliation_run r on r.id=e.run_id
               where r.engagement_id=$1 and (r.recon_type like 'GST_%' or r.recon_type='TDS_RECONCILIATION' or r.recon_type like 'PAYROLL_%')""",
            engagement_id) or 0

        results = [
            test_p2p_vendor_master(dup_pairs),
            test_o2c_revenue_gst_completeness(gst_books_vs_gstr1),
            test_r2r_journal_override(je_counts["hc"] or 0, je_counts["total"] or 0),
            test_treasury_tb_balance_direction(tb_flagged),
            test_tax_statutory_reconciliation(total_statutory),
        ]

        for r in results:
            await conn.execute(
                """insert into ifc_test_result (engagement_id, control_id, test_result, exception_detail, tested_via, tested_by)
                   values ($1,$2,$3,$4,'AUTOMATED',$5)
                   on conflict (engagement_id, control_id) do update set
                     test_result=excluded.test_result, exception_detail=excluded.exception_detail,
                     tested_via='AUTOMATED', tested_by=excluded.tested_by, tested_at=now()""",
                engagement_id, r.control_id, r.result, r.detail, user.user_id,
            )

    return IfcRunResult(
        controls_tested=len(results),
        effective_count=sum(1 for r in results if r.result == "EFFECTIVE"),
        exception_count=sum(1 for r in results if r.result == "EXCEPTION_NOTED"),
    )


class IfcControlOut(BaseModel):
    control_id: str
    process: str
    control_description: str
    control_type: str
    frequency: str
    automatable: bool
    test_result: str | None
    exception_detail: str | None
    tested_via: str | None


@router.get("", response_model=list[IfcControlOut])
async def list_ifc(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        rows = await conn.fetch(
            """select c.id as control_id, c.process, c.control_description, c.control_type, c.frequency, c.automatable,
                      t.test_result, t.exception_detail, t.tested_via
               from ifc_control c
               left join ifc_test_result t on t.control_id = c.id and t.engagement_id = $1
               order by c.process, c.id""",
            engagement_id,
        )
    return [IfcControlOut(**dict(r)) for r in rows]


class ManualTestRequest(BaseModel):
    test_result: str  # EFFECTIVE | EXCEPTION_NOTED | NOT_TESTED
    exception_detail: str | None = None


@router.put("/{control_id}", status_code=204)
async def record_manual_test(
    engagement_id: UUID, control_id: str, body: ManualTestRequest,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    if body.test_result not in ("EFFECTIVE", "EXCEPTION_NOTED", "NOT_TESTED"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "test_result must be EFFECTIVE, EXCEPTION_NOTED, or NOT_TESTED")
    async with tenant_conn(user.firm_id) as conn:
        control = await conn.fetchrow("select id from ifc_control where id=$1", control_id)
        if not control:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Control not found")
        await conn.execute(
            """insert into ifc_test_result (engagement_id, control_id, test_result, exception_detail, tested_via, tested_by)
               values ($1,$2,$3,$4,'MANUAL',$5)
               on conflict (engagement_id, control_id) do update set
                 test_result=excluded.test_result, exception_detail=excluded.exception_detail,
                 tested_via='MANUAL', tested_by=excluded.tested_by, tested_at=now()""",
            engagement_id, control_id, body.test_result, body.exception_detail, user.user_id,
        )
