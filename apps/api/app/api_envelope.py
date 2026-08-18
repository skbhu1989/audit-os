"""
Standard API response envelope (Sections 49-50 of the API/Integration spec).

Scoped deliberately to the NEW integration-layer endpoints built in this
phase (Integration Centre, Universal Import, Universal Reconciliation) —
retrofitting this envelope onto the ~30 existing routers built across prior
phases would be a large, risky change to already-tested working code, which
the spec's own "do not rebuild existing functionality" principle argues
against. Documented as a scoping decision, not an oversight.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any


def envelope(data: Any, source: str = "internal") -> dict:
    return {
        "success": True,
        "data": data,
        "meta": {
            "request_id": f"REQ-{uuid.uuid4().hex[:12]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "version": "v1",
        },
    }


def error_envelope(error_code: str, message: str, retryable: bool = False, fallback_available: bool = False) -> dict:
    return {
        "success": False,
        "error_code": error_code,
        "message": message,
        "retryable": retryable,
        "fallback_available": fallback_available,
        "request_id": f"REQ-{uuid.uuid4().hex[:12]}",
    }
