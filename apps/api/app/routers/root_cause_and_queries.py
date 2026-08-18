from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, require_roles, CurrentUser
from ..root_cause import classify_root_cause
from ..management_query import draft_client_query

router = APIRouter(tags=["root-cause-and-queries"])
WRITE_ROLES = ("FIRM_ADMIN", "PARTNER", "MANAGER", "SENIOR")


class RootCauseOut(BaseModel):
    exception_id: UUID
    module: str | None
    reason: str | None
    risk_level: str
    root_cause: str
    what: str
    why: str
    impact: str
    action: str


@router.get("/engagements/{engagement_id}/exceptions/{exception_id}/root-cause", response_model=RootCauseOut)
async def get_root_cause(engagement_id: UUID, exception_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        exc = await conn.fetchrow(
            "select module, reason, risk_level, created_at from audit_exception where id=$1 and engagement_id=$2",
            exception_id, engagement_id,
        )
        if not exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Exception not found")

        age_days = None
        if exc["module"] in ("AP", "AR") and exc["reason"]:
            import re
            m = re.search(r"outstanding (\d+) days", exc["reason"])
            if m:
                age_days = int(m.group(1))

    rc = classify_root_cause(exc["module"], exc["reason"], exc["risk_level"], age_days)
    return RootCauseOut(
        exception_id=exception_id, module=exc["module"], reason=exc["reason"], risk_level=exc["risk_level"],
        root_cause=rc.root_cause, what=rc.what, why=rc.why, impact=rc.impact, action=rc.action,
    )


class DraftQueryRequest(BaseModel):
    days_to_respond: int = 7


class QueryOut(BaseModel):
    id: UUID
    exception_id: UUID | None
    query_text: str
    required_information: str | None
    due_date: str | None
    status: str
    client_response: str | None


@router.post("/engagements/{engagement_id}/exceptions/{exception_id}/draft-query", response_model=QueryOut, status_code=201)
async def draft_query_for_exception(
    engagement_id: UUID, exception_id: UUID, body: DraftQueryRequest,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    async with tenant_conn(user.firm_id) as conn:
        exc = await conn.fetchrow(
            "select module, reason, amount, difference, risk_level from audit_exception where id=$1 and engagement_id=$2",
            exception_id, engagement_id,
        )
        if not exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Exception not found")

        rc = classify_root_cause(exc["module"], exc["reason"], exc["risk_level"])
        amt = exc["amount"] if exc["amount"] is not None else exc["difference"]
        draft = draft_client_query(
            exc["module"] or "General", exc["reason"] or "", float(amt) if amt is not None else None,
            rc.root_cause, body.days_to_respond,
        )

        row = await conn.fetchrow(
            """insert into audit_query (engagement_id, exception_id, query_text, required_information, due_date, raised_by, status)
               values ($1,$2,$3,$4,$5,$6,'OPEN') returning id, exception_id, query_text, required_information, due_date, status, client_response""",
            engagement_id, exception_id, draft.query_text, draft.required_information, draft.due_date, user.user_id,
        )
        # move the exception into CLIENT_RESPONSE-pending state so the
        # exception list and this query stay in sync
        await conn.execute(
            "update audit_exception set status='ASSIGNED', updated_at=now() where id=$1 and status='OPEN'",
            exception_id,
        )
    return QueryOut(
        id=row["id"], exception_id=row["exception_id"], query_text=row["query_text"],
        required_information=row["required_information"], due_date=str(row["due_date"]) if row["due_date"] else None,
        status=row["status"], client_response=row["client_response"],
    )


@router.get("/engagements/{engagement_id}/queries", response_model=list[QueryOut])
async def list_queries(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        rows = await conn.fetch(
            """select id, exception_id, query_text, required_information, due_date, status, client_response
               from audit_query where engagement_id=$1 order by raised_at desc""",
            engagement_id,
        )
    return [
        QueryOut(
            id=r["id"], exception_id=r["exception_id"], query_text=r["query_text"],
            required_information=r["required_information"], due_date=str(r["due_date"]) if r["due_date"] else None,
            status=r["status"], client_response=r["client_response"],
        ) for r in rows
    ]


class RespondQueryRequest(BaseModel):
    client_response: str
    status: str = "RESPONDED"


@router.patch("/engagements/{engagement_id}/queries/{query_id}", status_code=204)
async def respond_to_query(
    engagement_id: UUID, query_id: UUID, body: RespondQueryRequest, user: CurrentUser = Depends(get_current_user)
):
    if body.status not in ("OPEN", "RESPONDED", "OVERDUE", "CLOSED"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "status must be OPEN, RESPONDED, OVERDUE, or CLOSED")
    async with tenant_conn(user.firm_id) as conn:
        existing = await conn.fetchrow("select id from audit_query where id=$1 and engagement_id=$2", query_id, engagement_id)
        if not existing:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Query not found")
        await conn.execute(
            "update audit_query set client_response=$1, status=$2, responded_at=now() where id=$3",
            body.client_response, body.status, query_id,
        )
