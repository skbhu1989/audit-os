"""
Inventory Audit (Section 72): valuation, ageing, and GL reconciliation.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class InventoryValuationFlag:
    item_code: str | None
    description: str
    cost_value: float | None
    nrv_value: float | None
    write_down_required: float | None
    ageing_category: str  # 'NORMAL' | 'SLOW_MOVING' | 'OBSOLETE' | 'UNKNOWN'


def classify_ageing(ageing_days: int | None) -> str:
    if ageing_days is None:
        return "UNKNOWN"
    if ageing_days > 365:
        return "OBSOLETE"
    if ageing_days > 180:
        return "SLOW_MOVING"
    return "NORMAL"


def assess_item(item: dict) -> InventoryValuationFlag:
    """item: {'item_code','description','quantity_on_hand','unit_cost','nrv','ageing_days'}."""
    qty = item["quantity_on_hand"]
    unit_cost = item.get("unit_cost")
    nrv = item.get("nrv")

    cost_value = qty * unit_cost if unit_cost is not None else None
    nrv_value = qty * nrv if nrv is not None else None

    write_down = None
    if cost_value is not None and nrv_value is not None and nrv_value < cost_value:
        write_down = round(cost_value - nrv_value, 2)

    return InventoryValuationFlag(
        item.get("item_code"), item["description"], cost_value, nrv_value, write_down,
        classify_ageing(item.get("ageing_days")),
    )


@dataclass
class InventoryGlReconciliation:
    inventory_total: float
    gl_total: float
    difference: float
    status: str  # 'MATCHED' | 'MISMATCH' | 'NO_DATA'


def reconcile_inventory_to_gl(inventory_cost_total: float, gl_inventory_balance: float | None) -> InventoryGlReconciliation:
    if gl_inventory_balance is None:
        return InventoryGlReconciliation(inventory_cost_total, 0.0, inventory_cost_total, "NO_DATA")
    diff = round(inventory_cost_total - gl_inventory_balance, 2)
    status = "MATCHED" if abs(diff) < 1.0 else "MISMATCH"
    return InventoryGlReconciliation(inventory_cost_total, gl_inventory_balance, diff, status)
