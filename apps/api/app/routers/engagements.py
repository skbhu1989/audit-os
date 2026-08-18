from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from uuid import UUID
from datetime import date

from ..db import tenant_conn
from ..deps import get_current_user, require_roles, CurrentUser

router = APIRouter(prefix="/engagements", tags=["engagements"])

WRITE_ROLES = ("FIRM_ADMIN", "PARTNER", "MANAGER")


class EngagementCreate(BaseModel):
    client_id: UUID
    financial_year: str
    reporting_date: date
    framework: str
    materiality_benchmark: str | None = None


class EngagementOut(BaseModel):
    id: UUID
    client_id: UUID
    financial_year: str
    reporting_date: date
    framework: str
    status: str
    overall_materiality: float | None
    performance_materiality: float | None
    engagement_partner_id: UUID | None
    engagement_manager_id: UUID | None


@router.get("", response_model=list[EngagementOut])
async def list_engagements(
    client_id: UUID | None = None, user: CurrentUser = Depends(get_current_user)
):
    async with tenant_conn(user.firm_id) as conn:
        if client_id:
            rows = await conn.fetch(
                """select id, client_id, financial_year, reporting_date, framework, status,
                          overall_materiality, performance_materiality,
                          engagement_partner_id, engagement_manager_id
                   from engagement where client_id = $1 order by reporting_date desc""",
                client_id,
            )
        else:
            rows = await conn.fetch(
                """select id, client_id, financial_year, reporting_date, framework, status,
                          overall_materiality, performance_materiality,
                          engagement_partner_id, engagement_manager_id
                   from engagement order by reporting_date desc"""
            )
    return [EngagementOut(**dict(r)) for r in rows]


@router.post("", response_model=EngagementOut, status_code=201)
async def create_engagement(
    body: EngagementCreate, user: CurrentUser = Depends(require_roles(*WRITE_ROLES))
):
    async with tenant_conn(user.firm_id) as conn:
        # Confirm the client belongs to this firm before attaching an engagement
        # to it — belt-and-braces on top of RLS, and gives a clean 404 instead
        # of a foreign-key error if someone passes a client_id from elsewhere.
        owned = await conn.fetchrow("select 1 from client where id = $1", body.client_id)
        if not owned:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

        try:
            row = await conn.fetchrow(
                """insert into engagement (client_id, financial_year, reporting_date,
                                             framework, materiality_benchmark, engagement_partner_id)
                   values ($1,$2,$3,$4,$5,$6)
                   returning id, client_id, financial_year, reporting_date, framework, status,
                             overall_materiality, performance_materiality,
                             engagement_partner_id, engagement_manager_id""",
                body.client_id, body.financial_year, body.reporting_date,
                body.framework, body.materiality_benchmark,
                user.user_id if user.role == "PARTNER" else None,
            )
        except Exception as e:
            if "unique" in str(e).lower():
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    f"An engagement for FY {body.financial_year} already exists for this client",
                )
            raise
    return EngagementOut(**dict(row))


class MaterialityUpdate(BaseModel):
    overall_materiality: float
    performance_materiality: float
    materiality_benchmark: str
    rationale: str | None = None  # required for override per Section P; logged to audit trail via trigger


@router.patch("/{engagement_id}/materiality", response_model=EngagementOut)
async def set_materiality(
    engagement_id: UUID,
    body: MaterialityUpdate,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    async with tenant_conn(user.firm_id) as conn:
        row = await conn.fetchrow(
            """update engagement set overall_materiality = $1, performance_materiality = $2,
                      materiality_benchmark = $3, updated_at = now()
               where id = $4
               returning id, client_id, financial_year, reporting_date, framework, status,
                         overall_materiality, performance_materiality,
                         engagement_partner_id, engagement_manager_id""",
            body.overall_materiality, body.performance_materiality,
            body.materiality_benchmark, engagement_id,
        )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")
    return EngagementOut(**dict(row))


class TeamAssignment(BaseModel):
    user_id: UUID
    engagement_role: str


@router.post("/{engagement_id}/team", status_code=204)
async def assign_team_member(
    engagement_id: UUID, body: TeamAssignment,
    user: CurrentUser = Depends(require_roles("FIRM_ADMIN", "PARTNER", "MANAGER")),
):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id = $1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")
        member = await conn.fetchrow("select 1 from app_user where id = $1", body.user_id)
        if not member:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found in this firm")
        await conn.execute(
            """insert into engagement_team (engagement_id, user_id, engagement_role)
               values ($1,$2,$3)
               on conflict (engagement_id, user_id) do update set engagement_role = excluded.engagement_role""",
            engagement_id, body.user_id, body.engagement_role,
        )


class PeriodCreate(BaseModel):
    label: str
    start_date: date
    end_date: date


class PeriodOut(BaseModel):
    id: UUID
    label: str
    start_date: date
    end_date: date
    close_status: str


@router.post("/{engagement_id}/periods", response_model=PeriodOut, status_code=201)
async def create_period(
    engagement_id: UUID, body: PeriodCreate,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id = $1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")
        row = await conn.fetchrow(
            """insert into period (engagement_id, label, start_date, end_date)
               values ($1,$2,$3,$4)
               returning id, label, start_date, end_date, close_status""",
            engagement_id, body.label, body.start_date, body.end_date,
        )
    return PeriodOut(**dict(row))


@router.get("/{engagement_id}/periods", response_model=list[PeriodOut])
async def list_periods(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        rows = await conn.fetch(
            """select id, label, start_date, end_date, close_status
               from period where engagement_id = $1 order by start_date""",
            engagement_id,
        )
    return [PeriodOut(**dict(r)) for r in rows]
