from uuid import UUID
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, CurrentUser
from ..fixed_asset import check_depreciation_consistency, reconcile_far_to_gl
from ..inventory import assess_item, reconcile_inventory_to_gl

router = APIRouter(prefix="/engagements/{engagement_id}", tags=["fixed-assets-inventory"])


class FarRowOut(BaseModel):
    asset_code: str | None
    description: str
    category: str | None
    gross_block: float
    accum_depreciation: float
    net_block: float
    expected_accum_depreciation: float | None
    flag: str | None
    physically_verified: bool


class FarSummaryOut(BaseModel):
    assets: list[FarRowOut]
    far_gross_total: float
    gl_ppe_balance: float | None
    reconciliation_status: str
    reconciliation_difference: float


@router.get("/fixed-assets", response_model=FarSummaryOut)
async def get_fixed_assets(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select reporting_date from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        rows = await conn.fetch(
            """select asset_code, description, category, acquisition_date, gross_block, accum_depreciation,
                      net_block, useful_life_years, depreciation_method, disposal_date, physically_verified
               from fixed_asset where engagement_id=$1""",
            engagement_id,
        )
        gl_ppe = await conn.fetchval(
            """select sum(t.debit - t.credit) from trial_balance_line t join account a on a.id=t.account_id
               where t.engagement_id=$1 and a.note_ref='Property, Plant and Equipment'""",
            engagement_id,
        )

    out_rows = []
    for r in rows:
        asset_dict = {
            "asset_code": r["asset_code"], "description": r["description"],
            "gross_block": float(r["gross_block"]), "accum_depreciation": float(r["accum_depreciation"]),
            "useful_life_years": float(r["useful_life_years"]) if r["useful_life_years"] else None,
            "depreciation_method": r["depreciation_method"], "acquisition_date": r["acquisition_date"],
            "disposal_date": r["disposal_date"],
        }
        dep = check_depreciation_consistency(asset_dict, eng["reporting_date"])
        out_rows.append(FarRowOut(
            asset_code=r["asset_code"], description=r["description"], category=r["category"],
            gross_block=float(r["gross_block"]), accum_depreciation=float(r["accum_depreciation"]),
            net_block=float(r["net_block"]), expected_accum_depreciation=dep.expected_accum_depreciation,
            flag=dep.flag, physically_verified=r["physically_verified"],
        ))

    far_total = sum(r.gross_block for r in out_rows)
    recon = reconcile_far_to_gl(far_total, float(gl_ppe) if gl_ppe is not None else None)

    return FarSummaryOut(
        assets=out_rows, far_gross_total=far_total, gl_ppe_balance=recon.gl_total if recon.status != "NO_DATA" else None,
        reconciliation_status=recon.status, reconciliation_difference=recon.difference,
    )


class InventoryRowOut(BaseModel):
    item_code: str | None
    description: str
    quantity_on_hand: float
    cost_value: float | None
    nrv_value: float | None
    write_down_required: float | None
    ageing_category: str


class InventorySummaryOut(BaseModel):
    items: list[InventoryRowOut]
    inventory_cost_total: float
    gl_inventory_balance: float | None
    reconciliation_status: str
    reconciliation_difference: float
    total_write_down_required: float
    slow_moving_count: int
    obsolete_count: int


@router.get("/inventory", response_model=InventorySummaryOut)
async def get_inventory(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        rows = await conn.fetch(
            "select item_code, description, quantity_on_hand, unit_cost, nrv, ageing_days from inventory_item where engagement_id=$1",
            engagement_id,
        )
        gl_inv = await conn.fetchval(
            """select sum(t.debit - t.credit) from trial_balance_line t join account a on a.id=t.account_id
               where t.engagement_id=$1 and a.note_ref='Inventories'""",
            engagement_id,
        )

    out_rows = []
    for r in rows:
        item_dict = {
            "item_code": r["item_code"], "description": r["description"], "quantity_on_hand": float(r["quantity_on_hand"]),
            "unit_cost": float(r["unit_cost"]) if r["unit_cost"] is not None else None,
            "nrv": float(r["nrv"]) if r["nrv"] is not None else None,
            "ageing_days": r["ageing_days"],
        }
        a = assess_item(item_dict)
        out_rows.append(InventoryRowOut(
            item_code=a.item_code, description=a.description, quantity_on_hand=float(r["quantity_on_hand"]),
            cost_value=a.cost_value, nrv_value=a.nrv_value, write_down_required=a.write_down_required,
            ageing_category=a.ageing_category,
        ))

    cost_total = sum(r.cost_value for r in out_rows if r.cost_value is not None)
    recon = reconcile_inventory_to_gl(cost_total, float(gl_inv) if gl_inv is not None else None)

    return InventorySummaryOut(
        items=out_rows, inventory_cost_total=cost_total,
        gl_inventory_balance=recon.gl_total if recon.status != "NO_DATA" else None,
        reconciliation_status=recon.status, reconciliation_difference=recon.difference,
        total_write_down_required=sum(r.write_down_required for r in out_rows if r.write_down_required),
        slow_moving_count=sum(1 for r in out_rows if r.ageing_category == "SLOW_MOVING"),
        obsolete_count=sum(1 for r in out_rows if r.ageing_category == "OBSOLETE"),
    )
