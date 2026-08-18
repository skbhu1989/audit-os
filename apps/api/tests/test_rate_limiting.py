"""
Rate limiter regression test.

Tests the underlying rate_limit() logic directly rather than through a real
app request — app.rate_limit._DISABLED is intentionally True whenever
ENVIRONMENT=test (see that module's own comment: TestClient's requests all
share one fake client address, which would otherwise collide every test's
firm-creation call into a single bucket). That disable is correctly scoped
to app-level requests; it should never be a reason the limiter's own core
logic goes unverified.
"""
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException

import app.rate_limit as rate_limit_module


def _fake_request(path: str, ip: str):
    req = MagicMock()
    req.url.path = path
    req.headers = {}
    req.client.host = ip
    return req


@pytest.mark.asyncio
async def test_rate_limiter_blocks_after_threshold_and_isolates_clients():
    original_disabled = rate_limit_module._DISABLED
    rate_limit_module._DISABLED = False
    try:
        limiter = rate_limit_module.rate_limit(max_requests=3, window_seconds=60)
        req_a = _fake_request("/test-endpoint", "9.9.9.1")

        for i in range(3):
            await limiter(req_a)  # must not raise

        with pytest.raises(HTTPException) as exc_info:
            await limiter(req_a)
        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers

        # A different client must not be affected by client A's limit.
        req_b = _fake_request("/test-endpoint", "9.9.9.2")
        await limiter(req_b)  # must not raise
    finally:
        rate_limit_module._DISABLED = original_disabled


@pytest.mark.asyncio
async def test_rate_limiter_respects_x_forwarded_for():
    """Behind a reverse proxy (the normal deployment shape), the real
    client IP arrives via X-Forwarded-For, not the direct connection —
    verifies the limiter actually reads it rather than rate-limiting the
    proxy's own address for every real client."""
    original_disabled = rate_limit_module._DISABLED
    rate_limit_module._DISABLED = False
    try:
        limiter = rate_limit_module.rate_limit(max_requests=1, window_seconds=60)

        req1 = _fake_request("/proxied", "10.0.0.1")  # the proxy's own address
        req1.headers = {"x-forwarded-for": "203.0.113.5"}
        await limiter(req1)

        req2 = _fake_request("/proxied", "10.0.0.1")  # same proxy, different real client
        req2.headers = {"x-forwarded-for": "203.0.113.99"}
        await limiter(req2)  # must not raise — different real client behind the same proxy

        req3 = _fake_request("/proxied", "10.0.0.1")
        req3.headers = {"x-forwarded-for": "203.0.113.5"}  # same real client as req1 again
        with pytest.raises(HTTPException):
            await limiter(req3)
    finally:
        rate_limit_module._DISABLED = original_disabled
