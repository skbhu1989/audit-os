from fastapi import APIRouter, Depends, HTTPException, status
from ..db import tenant_conn
from ..deps import get_current_user, CurrentUser
from ..api_envelope import envelope, error_envelope

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


@router.get("")
async def list_integrations(user: CurrentUser = Depends(get_current_user)):
    """Section 41: Integration Centre. Every row here reflects the REAL
    state — status is NOT_CONNECTED for every external provider in this
    build, per Section 44's explicit prohibition on faking connectivity.
    No tenant scoping needed: this is platform-level provider metadata,
    not client data."""
    async with tenant_conn(user.firm_id) as conn:
        rows = await conn.fetch(
            """select id, display_name, category, classification, classification_reason, status,
                      auth_type, fallback_available, fallback_description,
                      last_successful_sync, last_failed_sync, last_error
               from integration_provider order by category, display_name"""
        )
    data = [
        {
            "id": r["id"], "display_name": r["display_name"], "category": r["category"],
            "classification": r["classification"], "classification_reason": r["classification_reason"],
            "status": r["status"], "auth_type": r["auth_type"],
            "fallback_available": r["fallback_available"], "fallback_description": r["fallback_description"],
            "last_successful_sync": r["last_successful_sync"].isoformat() if r["last_successful_sync"] else None,
            "last_failed_sync": r["last_failed_sync"].isoformat() if r["last_failed_sync"] else None,
            "last_error": r["last_error"],
        }
        for r in rows
    ]
    return envelope(data, source="integration_registry")


@router.post("/{provider_id}/test")
async def test_integration(provider_id: str, user: CurrentUser = Depends(get_current_user)):
    """Section 41's 'TEST' button. This NEVER simulates success — every
    provider in this build is genuinely NOT_CONNECTED (no credentials
    configured anywhere in this environment), so the honest response is
    always a clear failure with the real reason and the fallback path,
    per Section 30's fallback pattern and Section 44's no-fake-API rule."""
    async with tenant_conn(user.firm_id) as conn:
        row = await conn.fetchrow("select * from integration_provider where id=$1", provider_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown provider '{provider_id}'")

    result = error_envelope(
        error_code=f"{row['category']}_NOT_CONFIGURED",
        message=(
            f"{row['display_name']} is not connected. {row['classification_reason']} "
            f"No credentials are configured for this provider in this environment."
        ),
        retryable=False,
        fallback_available=row["fallback_available"],
    )
    result["fallback_description"] = row["fallback_description"]
    return result


@router.post("/{provider_id}/connect")
async def connect_integration(provider_id: str, user: CurrentUser = Depends(get_current_user)):
    """Deliberately not implemented as a real OAuth/API-key flow — doing so
    without an actual registered application (Zoho, GSP/ASP, etc.) would
    mean either faking success (forbidden by Section 44) or building a UI
    for a flow that can never complete. Returns a clear, honest 501."""
    async with tenant_conn(user.firm_id) as conn:
        row = await conn.fetchrow("select display_name, auth_type from integration_provider where id=$1", provider_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown provider '{provider_id}'")
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        f"Connecting to {row['display_name']} requires {row['auth_type'] or 'credentials'} that are not "
        f"configured in this environment. This endpoint intentionally does not simulate a successful "
        f"connection — see the provider's fallback_description for the file-upload alternative.",
    )
