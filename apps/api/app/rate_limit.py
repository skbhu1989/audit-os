"""
Minimal in-memory rate limiting for the auth endpoints (login, signup) —
the two most abuse-prone routes in the system: unlimited login attempts
enable credential stuffing, unlimited signups enable junk-firm spam (the
firm INSERT is deliberately RLS-permissive to support bootstrap signup,
which was an accepted tradeoff *assuming* some rate limit existed — it
didn't, until now).

Honest limitation, stated plainly: this is in-memory, per-process state.
It resets on restart and does NOT coordinate across multiple server
instances behind a load balancer — a real horizontally-scaled deployment
needs a shared store (Redis) for this to be meaningful. No Redis/caching
layer exists anywhere in this build (a gap documented since Phase 4), so a
correctly-scoped choice here is a real, working single-instance limiter
now rather than a more "correct" design that can't actually be built
without infrastructure this system doesn't have.
"""
import os
import time
from collections import defaultdict
from fastapi import HTTPException, Request, status

_attempts: dict[str, list[float]] = defaultdict(list)

# The test suite creates a fresh firm via a real /auth/signup call for
# nearly every test (conftest.py's firm_a/firm_b fixtures) — and FastAPI's
# TestClient reports one fixed fake client address for every request in a
# session, so every test's signup collided into the same rate-limit bucket
# after ~5 tests. Not a reason to weaken the limiter for real traffic —
# conftest.py sets ENVIRONMENT=test explicitly, so this only disables
# limiting in that specific, deliberate context.
_DISABLED = os.environ.get("ENVIRONMENT") == "test"


def _client_key(request: Request) -> str:
    # X-Forwarded-For first (real client IP behind a reverse proxy, the
    # normal deployment shape), falling back to the direct connection.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(max_requests: int, window_seconds: int):
    """Dependency factory. Sliding window: counts requests from this client
    to this specific limiter instance within the trailing window_seconds."""

    async def _check(request: Request):
        if _DISABLED:
            return
        key = f"{request.url.path}:{_client_key(request)}"
        now = time.time()
        window_start = now - window_seconds

        recent = [t for t in _attempts[key] if t > window_start]
        if len(recent) >= max_requests:
            retry_after = int(recent[0] + window_seconds - now) + 1
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Too many requests. Try again in {retry_after} second(s).",
                headers={"Retry-After": str(retry_after)},
            )

        recent.append(now)
        _attempts[key] = recent

    return _check
