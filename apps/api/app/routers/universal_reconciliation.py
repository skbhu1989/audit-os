from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..deps import require_roles, get_current_user, CurrentUser
from ..api_envelope import envelope
from .reconciliation import run_gst_reconciliation, run_tds_reconciliation, run_payroll_reconciliation
from .bank_and_challan import get_bank_reconciliation, get_challan_mapping
from .fixed_assets_inventory import get_fixed_assets, get_inventory
from .loans_investments import get_loans, get_investments
from .intercompany import get_intercompany

router = APIRouter(prefix="/api/v1/reconciliation", tags=["universal-reconciliation"])
WRITE_ROLES = ("FIRM_ADMIN", "PARTNER", "MANAGER", "SENIOR")

# Section 28's examples (Books↔GST, Books↔TDS, Books↔Bank, Books↔FAR,
# Books↔Inventory, Books↔Payroll) mapped onto the actual, already-tested
# engines built in prior phases. Each entry is (async_fn, needs_extra_param).
# GST dispatches the full Books-vs-GSTR1/Purchase-vs-GSTR2B/GSTR1-vs-GSTR3B
# set together (that's how the underlying engine already runs, per Phase 6)
# rather than isolating a single pair — documented, not silently narrowed.
RECONCILIATION_REGISTRY = {
    "GST": {"fn": run_gst_reconciliation, "kind": "run", "description": "Books vs GSTR-1, Purchase vs GSTR-2B, GSTR-1 vs GSTR-3B"},
    "TDS": {"fn": run_tds_reconciliation, "kind": "run", "description": "TDS ledger vs challan vs return"},
    "PAYROLL": {"fn": run_payroll_reconciliation, "kind": "run", "description": "PF/ESI/PT liability vs challan"},
    "BANK": {"fn": get_bank_reconciliation, "kind": "read", "description": "Bank statement vs GL bank ledger"},
    "CHALLAN": {"fn": get_challan_mapping, "kind": "read_with_param", "param": "statutory_type", "description": "Statutory challan vs bank statement (requires statutory_type: GST/TDS/PF/ESI/PT)"},
    "FAR": {"fn": get_fixed_assets, "kind": "read", "description": "Fixed Asset Register vs GL"},
    "INVENTORY": {"fn": get_inventory, "kind": "read", "description": "Inventory Register vs GL"},
    "LOANS": {"fn": get_loans, "kind": "read", "description": "Loan Register vs GL"},
    "INVESTMENTS": {"fn": get_investments, "kind": "read", "description": "Investment Register vs GL"},
    "INTERCOMPANY": {"fn": get_intercompany, "kind": "read", "description": "Intercompany ledger vs counterparty confirmation"},
}


@router.get("/types")
async def list_reconciliation_types():
    """Documents exactly what's available through this unified endpoint —
    Section 28 asks for one reusable service; this is the honest inventory
    of what it actually dispatches to."""
    return envelope({k: v["description"] for k, v in RECONCILIATION_REGISTRY.items()})


class ReconciliationRequest(BaseModel):
    engagement_id: UUID
    reconciliation_type: str
    param: str | None = None  # e.g. statutory_type for CHALLAN


@router.post("")
async def run_reconciliation(body: ReconciliationRequest, user: CurrentUser = Depends(require_roles(*WRITE_ROLES))):
    entry = RECONCILIATION_REGISTRY.get(body.reconciliation_type.upper())
    if entry is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown reconciliation_type '{body.reconciliation_type}'. "
            f"Valid types: {', '.join(RECONCILIATION_REGISTRY.keys())}. See GET /api/v1/reconciliation/types.",
        )

    if entry["kind"] in ("run", "read"):
        result = await entry["fn"](engagement_id=body.engagement_id, user=user)
    elif entry["kind"] == "read_with_param":
        if not body.param:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"reconciliation_type '{body.reconciliation_type}' requires 'param': {entry['param']}")
        # Calling get_challan_mapping directly bypasses FastAPI's own
        # Query(..., pattern=...) validation for statutory_type (that
        # validation only runs through the HTTP request-parsing layer, not
        # on a direct Python call) — without this check, an invalid value
        # would only be caught by a raw Postgres enum error, not a clean
        # 400. Caught by tracing the reuse mechanism, not by a failed test.
        if body.reconciliation_type.upper() == "CHALLAN" and body.param not in ("GST", "TDS", "PF", "ESI", "PT"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "param (statutory_type) must be one of: GST, TDS, PF, ESI, PT")
        result = await entry["fn"](engagement_id=body.engagement_id, statutory_type=body.param, user=user)
    else:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Unhandled registry entry kind")

    result_dict = result.model_dump() if hasattr(result, "model_dump") else result
    return envelope(result_dict, source="internal_engine")
