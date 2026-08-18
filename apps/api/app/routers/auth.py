from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from uuid import uuid4

from ..db import system_conn, tenant_conn
from ..security import (
    hash_password, verify_password, issue_jwt,
    new_totp_secret, totp_provisioning_uri, verify_totp,
)
from ..deps import get_current_user, CurrentUser
from ..rate_limit import rate_limit
from fastapi import Depends

router = APIRouter(prefix="/auth", tags=["auth"])

# Signup gets the stricter limit — it's the more consequential abuse vector
# (unlimited junk firms), since the firm INSERT is deliberately RLS-permissive
# to support bootstrap signup at all (see migration 011's own comment).
# Login is more lenient since real users do mistype passwords.
_signup_limit = rate_limit(max_requests=5, window_seconds=3600)
_login_limit = rate_limit(max_requests=10, window_seconds=300)


class SignupRequest(BaseModel):
    firm_name: str
    icai_frn: str | None = None
    admin_email: EmailStr
    admin_name: str
    admin_password: str


class SignupResponse(BaseModel):
    firm_id: str
    user_id: str
    access_token: str


@router.post("/signup", response_model=SignupResponse, status_code=201)
async def signup(body: SignupRequest, _rl=Depends(_signup_limit)):
    """
    Bootstraps a brand-new firm + its first FIRM_ADMIN user.
    This is the one endpoint that legitimately runs before any tenant
    context exists (see db.py / migration 011 for why firm INSERT is
    the single RLS-permissive operation in the whole schema).
    """
    import asyncpg

    try:
        async with system_conn() as conn:
            # Generate the id client-side rather than relying on INSERT...RETURNING.
            # Postgres RLS applies the SELECT policy (not the INSERT policy) to
            # filter RETURNING output, and app.current_firm_id can't be set to a
            # value we don't have yet — so RETURNING would always come back empty.
            # Knowing the id up front lets us set tenant context first, then every
            # subsequent statement (including this one) satisfies its policy normally.
            firm_id = str(uuid4())
            await conn.execute("SELECT set_config('app.current_firm_id', $1, true)", firm_id)
            await conn.execute(
                "insert into firm (id, name, icai_frn) values ($1, $2, $3)",
                firm_id, body.firm_name, body.icai_frn,
            )

            user_id = str(uuid4())
            await conn.execute(
                """insert into app_user (id, firm_id, email, full_name, role)
                   values ($1, $2, $3, $4, 'FIRM_ADMIN')""",
                user_id, firm_id, body.admin_email, body.admin_name,
            )

            await conn.execute(
                "insert into app_user_credential (user_id, password_hash) values ($1, $2)",
                user_id, hash_password(body.admin_password),
            )
    except asyncpg.UniqueViolationError:
        # email is UNIQUE on app_user; this is the real (not RLS-blinded) check.
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    token = issue_jwt(user_id, firm_id, "FIRM_ADMIN")
    return SignupResponse(firm_id=firm_id, user_id=user_id, access_token=token)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    role: str
    mfa_required: bool = False


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, _rl=Depends(_login_limit)):
    async with system_conn() as conn:
        row = await conn.fetchrow(
            "select * from fn_authenticate_lookup($1)", body.email
        )
        if not row or not verify_password(body.password, row["password_hash"]):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
        if not row["is_active"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")

        if row["mfa_enabled"]:
            if not body.totp_code:
                return LoginResponse(access_token="", role=row["role"], mfa_required=True)
            if not verify_totp(row["mfa_secret"], body.totp_code):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid MFA code")

    token = issue_jwt(str(row["user_id"]), str(row["firm_id"]), row["role"])
    return LoginResponse(access_token=token, role=row["role"])


class MfaEnrollResponse(BaseModel):
    secret: str
    provisioning_uri: str


@router.post("/mfa/enroll", response_model=MfaEnrollResponse)
async def mfa_enroll(user: CurrentUser = Depends(get_current_user)):
    """Step 1 of MFA setup: generate a secret, not yet enabled until verified."""
    secret = new_totp_secret()
    async with tenant_conn(user.firm_id) as conn:
        row = await conn.fetchrow("select email from app_user where id = $1", user.user_id)
        await conn.execute(
            "update app_user set mfa_secret = $1 where id = $2", secret, user.user_id
        )
    return MfaEnrollResponse(secret=secret, provisioning_uri=totp_provisioning_uri(secret, row["email"]))


class MfaVerifyRequest(BaseModel):
    totp_code: str


@router.post("/mfa/verify", status_code=204)
async def mfa_verify(body: MfaVerifyRequest, user: CurrentUser = Depends(get_current_user)):
    """Step 2 of MFA setup: confirm the user's authenticator app is correctly
    synced before actually turning mfa_enabled on."""
    async with tenant_conn(user.firm_id) as conn:
        row = await conn.fetchrow("select mfa_secret from app_user where id = $1", user.user_id)
        if not row["mfa_secret"] or not verify_totp(row["mfa_secret"], body.totp_code):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid code — MFA not enabled")
        await conn.execute("update app_user set mfa_enabled = true where id = $1", user.user_id)
