from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose.exceptions import JWTError
from pydantic import BaseModel

from .security import decode_jwt

bearer_scheme = HTTPBearer()

# Permission matrix (Phase 1 architecture doc, Section 13), enforced here
# server-side — never trust a UI role gate alone.
ROLE_HIERARCHY = ["ARTICLE", "SENIOR", "EQCR_REVIEWER", "MANAGER", "PARTNER", "FIRM_ADMIN"]


class CurrentUser(BaseModel):
    user_id: str
    firm_id: str
    role: str


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> CurrentUser:
    try:
        payload = decode_jwt(creds.credentials)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return CurrentUser(user_id=payload["sub"], firm_id=payload["firm_id"], role=payload["role"])


def require_roles(*allowed_roles: str):
    """Dependency factory: 403s unless the caller's role is in allowed_roles.

    Usage: Depends(require_roles("PARTNER", "MANAGER", "FIRM_ADMIN"))
    """

    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role '{user.role}' is not permitted to perform this action "
                f"(requires one of: {', '.join(allowed_roles)})",
            )
        return user

    return _check
