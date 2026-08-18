from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, CurrentUser

router = APIRouter(prefix="/engagements/{engagement_id}/disclosure-checklist", tags=["financial-statements"])

# The standard Schedule III note categories this system's FS mapping engine
# (Phase 5's FS_MAPPING_RULES) actually produces note_ref values for.
# A category with zero mapped accounts isn't necessarily wrong — the entity
# may genuinely have no balance in that category — but it's a completeness
# signal worth surfacing rather than silently skipping.
EXPECTED_NOTE_CATEGORIES = [
    "Share Capital", "Reserves and Surplus", "Borrowings", "Trade Payables",
    "Other Current Liabilities", "Short-term Provisions", "Property, Plant and Equipment",
    "Capital Work-in-Progress", "Investments", "Trade Receivables",
    "Cash and Bank Balances", "Inventories", "Revenue from Operations",
    "Other Income", "Purchases", "Employee Benefit Expense", "Finance Costs",
    "Depreciation and Amortisation",
]


class ChecklistItemOut(BaseModel):
    note_category: str
    account_count: int
    approved_count: int  # mapped_by is set (human-approved, not just suggested)
    flagged_count: int   # accounts with an outstanding TB balance-direction flag
    status: str          # 'COMPLETE' | 'PENDING_APPROVAL' | 'NO_DATA' | 'FLAGGED'


class DisclosureChecklistOut(BaseModel):
    items: list[ChecklistItemOut]
    unmapped_account_count: int  # accounts with NO note_ref at all — not even suggested
    overall_status: str


@router.get("", response_model=DisclosureChecklistOut)
async def get_disclosure_checklist(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        rows = await conn.fetch(
            """select a.note_ref, a.mapped_by,
                      exists(select 1 from trial_balance_line t where t.account_id=a.id and t.flag is not null) as has_flag
               from account a where a.engagement_id=$1""",
            engagement_id,
        )
        unmapped = sum(1 for r in rows if r["note_ref"] is None)

        items = []
        for category in EXPECTED_NOTE_CATEGORIES:
            matching = [r for r in rows if r["note_ref"] == category]
            approved = sum(1 for r in matching if r["mapped_by"] is not None)
            flagged = sum(1 for r in matching if r["has_flag"])

            if not matching:
                item_status = "NO_DATA"
            elif flagged > 0:
                item_status = "FLAGGED"
            elif approved < len(matching):
                item_status = "PENDING_APPROVAL"
            else:
                item_status = "COMPLETE"

            items.append(ChecklistItemOut(
                note_category=category, account_count=len(matching), approved_count=approved,
                flagged_count=flagged, status=item_status,
            ))

    complete = sum(1 for i in items if i.status == "COMPLETE")
    overall = "COMPLETE" if complete == len(items) and unmapped == 0 else "INCOMPLETE"

    return DisclosureChecklistOut(items=items, unmapped_account_count=unmapped, overall_status=overall)
