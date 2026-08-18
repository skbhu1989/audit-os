import os
import time
import pyotp
import bcrypt
from jose import jwt
from jose.exceptions import JWTError  # noqa: F401 (re-exported for callers)

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    if ENVIRONMENT == "production":
        # Fail loudly at import time rather than silently deploying with a
        # publicly-known default secret — the exact gap flagged in the
        # pre-deploy review: nothing previously forced this.
        raise RuntimeError(
            "JWT_SECRET must be set via environment variable when ENVIRONMENT=production. "
            "Refusing to start with the development fallback secret."
        )
    JWT_SECRET = "dev-secret-change-me"
JWT_ALGORITHM = "HS256"
JWT_TTL_SECONDS = 60 * 60 * 8  # 8-hour session


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))


def issue_jwt(user_id: str, firm_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "firm_id": firm_id,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_TTL_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict:
    # Raises jwt.PyJWTError on expiry/tamper — caller converts to 401.
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, email: str, issuer: str = "AI Audit OS") -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)
