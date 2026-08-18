from uuid import UUID
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, require_roles, CurrentUser
from ..compliance_calendar import generate_calendar_items, compute_status

router = APIRouter(prefix="/engagements/{engagement_id}/compliance-calendar", tags=["compliance-calendar"])
WRITE_ROLES = ("FIRM_ADMIN", "PARTNER", "MANAGER", "SENIOR")


class GenerateResult(BaseModel):
    items_created: int
    items_skipped_existing: int


@router.post("/generate", response_model=GenerateResult)
async def generate_calendar(engagement_id: UUID, user: CurrentUser = Depends(require_roles(*WRITE_ROLES))):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select financial_year, reporting_date from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")
        # reporting_date is the FY end; FY start is 1 April of the prior calendar year
        # for a standard Indian FY (this assumes a standard Apr-Mar year, which is
        # true for nearly all Indian entities but not universally guaranteed).
        fy_end = eng["reporting_date"]
        fy_start = date(fy_end.year - 1 if fy_end.month <= 3 else fy_end.year, 4, 1)

        items = generate_calendar_items(fy_start, fy_end)
        created = 0
        skipped = 0
        for item in items:
            existing = await conn.fetchrow(
                """select id from compliance_calendar_item where engagement_id=$1 and statutory_type=$2
                   and filing_or_payment=$3 and period=$4""",
                engagement_id, item.statutory_type, item.filing_or_payment, item.period,
            )
            if existing:
                skipped += 1
                continue
            await conn.execute(
                """insert into compliance_calendar_item (engagement_id, statutory_type, filing_or_payment, period, due_date)
                   values ($1,$2,$3,$4,$5)""",
                engagement_id, item.statutory_type, item.filing_or_payment, item.period, item.due_date,
            )
            created += 1
    return GenerateResult(items_created=created, items_skipped_existing=skipped)


class RecordActualRequest(BaseModel):
    actual_date: date
    amount: float | None = None


@router.patch("/{item_id}", status_code=204)
async def record_actual(
    engagement_id: UUID, item_id: UUID, body: RecordActualRequest,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    async with tenant_conn(user.firm_id) as conn:
        item = await conn.fetchrow(
            "select due_date from compliance_calendar_item where id=$1 and engagement_id=$2", item_id, engagement_id
        )
        if not item:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Calendar item not found")
        s = compute_status(item["due_date"], body.actual_date, date.today())
        await conn.execute(
            "update compliance_calendar_item set actual_date=$1, amount=coalesce($2,amount), status=$3 where id=$4",
            body.actual_date, body.amount, s.status, item_id,
        )


class CalendarItemOut(BaseModel):
    id: UUID
    statutory_type: str
    filing_or_payment: str
    period: str
    due_date: date
    actual_date: date | None
    status: str
    delay_days: int | None


@router.get("", response_model=list[CalendarItemOut])
async def list_calendar(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        rows = await conn.fetch(
            """select id, statutory_type, filing_or_payment, period, due_date, actual_date, status
               from compliance_calendar_item where engagement_id=$1 order by due_date""",
            engagement_id,
        )
    today = date.today()
    out = []
    for r in rows:
        s = compute_status(r["due_date"], r["actual_date"], today)
        out.append(CalendarItemOut(
            id=r["id"], statutory_type=r["statutory_type"], filing_or_payment=r["filing_or_payment"],
            period=r["period"], due_date=r["due_date"], actual_date=r["actual_date"],
            status=s.status, delay_days=s.delay_days,
        ))
    return out
