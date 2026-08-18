from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from uuid import UUID

from ..db import tenant_conn
from ..deps import get_current_user, require_roles, CurrentUser

router = APIRouter(prefix="/clients", tags=["clients"])

WRITE_ROLES = ("FIRM_ADMIN", "PARTNER", "MANAGER")


class ClientCreate(BaseModel):
    legal_name: str
    cin: str | None = None
    pan: str | None = None
    tan: str | None = None
    gstin_primary: str | None = None
    industry: str | None = None
    listing_status: str = "UNLISTED"
    framework: str | None = None


class ClientOut(BaseModel):
    id: UUID
    legal_name: str
    cin: str | None
    pan: str | None
    tan: str | None
    gstin_primary: str | None
    industry: str | None
    listing_status: str
    framework: str | None


@router.get("", response_model=list[ClientOut])
async def list_clients(user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        rows = await conn.fetch(
            """select id, legal_name, cin, pan, tan, gstin_primary, industry,
                      listing_status, framework from client order by legal_name"""
        )
    return [ClientOut(**dict(r)) for r in rows]


@router.post("", response_model=ClientOut, status_code=201)
async def create_client(
    body: ClientCreate,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    async with tenant_conn(user.firm_id) as conn:
        row = await conn.fetchrow(
            """insert into client (firm_id, legal_name, cin, pan, tan, gstin_primary,
                                     industry, listing_status, framework)
               values ($1,$2,$3,$4,$5,$6,$7,$8,$9)
               returning id, legal_name, cin, pan, tan, gstin_primary, industry,
                         listing_status, framework""",
            user.firm_id, body.legal_name, body.cin, body.pan, body.tan,
            body.gstin_primary, body.industry, body.listing_status, body.framework,
        )
    return ClientOut(**dict(row))


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(client_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        row = await conn.fetchrow(
            """select id, legal_name, cin, pan, tan, gstin_primary, industry,
                      listing_status, framework from client where id = $1""",
            client_id,
        )
    if not row:
        # RLS means this also fires for another firm's client id — which is
        # exactly the right behaviour: a 404, not a 403, so existence of
        # other tenants' data is never leaked via status code.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return ClientOut(**dict(row))
