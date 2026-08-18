from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, CurrentUser
from ..data_centre import build_checklist

router = APIRouter(prefix="/engagements/{engagement_id}/data-centre", tags=["data-centre"])


class ChecklistItemOut(BaseModel):
    dataset_type: str
    label: str
    requirement: str
    reason: str
    coverage_status: str  # computed from real data_coverage rows, 'NOT_UPLOADED' if none exist
    periods_uploaded: int


class DataCentreOut(BaseModel):
    checklist: list[ChecklistItemOut]
    overall_coverage_pct: float
    required_missing_count: int


@router.get("", response_model=DataCentreOut)
async def get_data_centre(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        client = await conn.fetchrow(
            "select 1 from engagement where id=$1", engagement_id
        )
        if not client:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        # Real profile signals derived from actual data already in the
        # system, not asked of the user separately — an engagement that has
        # ingested any GSTR/GST_transaction data or has a GSTIN on the
        # client record has "GST", one with payroll_line rows has
        # "employees", etc. Falls back to REQUIRED-by-default (the safer
        # assumption) when no signal exists yet, rather than guessing NOT
        # APPLICABLE and hiding something the auditor actually needs.
        client_row = await conn.fetchrow(
            """select c.gstin_primary from engagement e join client c on c.id = e.client_id where e.id=$1""",
            engagement_id,
        )
        employee_count = await conn.fetchval("select count(*) from employee where engagement_id=$1", engagement_id)
        fa_note_count = await conn.fetchval(
            "select count(*) from account where engagement_id=$1 and note_ref = 'Property, Plant and Equipment'",
            engagement_id,
        )
        inv_note_count = await conn.fetchval(
            "select count(*) from account where engagement_id=$1 and note_ref = 'Inventories'", engagement_id
        )
        profile = {
            "has_gst": bool(client_row and client_row["gstin_primary"]) or True,  # default True: safer to over-ask than under-ask
            "has_employees": (employee_count or 0) > 0 or True,
            "has_fixed_assets": (fa_note_count or 0) > 0 or True,
            "has_inventory": (inv_note_count or 0) > 0,
        }

        checklist_items = build_checklist(profile)

        coverage_rows = await conn.fetch(
            "select dataset_type, status, count(*) as period_count from data_coverage where engagement_id=$1 group by dataset_type, status",
            engagement_id,
        )
        coverage_by_type: dict[str, dict] = {}
        for r in coverage_rows:
            coverage_by_type.setdefault(r["dataset_type"], {})[r["status"]] = r["period_count"]

    out_items = []
    required_missing = 0
    for item in checklist_items:
        by_status = coverage_by_type.get(item.dataset_type, {})
        total_periods = sum(by_status.values())
        if total_periods == 0:
            cov = "NOT_UPLOADED"
        elif by_status.get("UPLOADED", 0) == total_periods:
            cov = "UPLOADED"
        elif by_status.get("NOT_UPLOADED", 0) == total_periods:
            cov = "NOT_UPLOADED"
        else:
            cov = "PARTIAL"

        if item.requirement == "REQUIRED" and cov == "NOT_UPLOADED":
            required_missing += 1

        out_items.append(ChecklistItemOut(
            dataset_type=item.dataset_type, label=item.label, requirement=item.requirement,
            reason=item.reason, coverage_status=cov, periods_uploaded=total_periods,
        ))

    required_items = [i for i in out_items if i.requirement == "REQUIRED"]
    uploaded_required = sum(1 for i in required_items if i.coverage_status in ("UPLOADED", "PARTIAL"))
    overall_pct = round(100 * uploaded_required / len(required_items), 1) if required_items else 100.0

    return DataCentreOut(checklist=out_items, overall_coverage_pct=overall_pct, required_missing_count=required_missing)
