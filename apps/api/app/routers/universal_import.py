from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status

from ..db import tenant_conn
from ..deps import require_roles, get_current_user, CurrentUser
from ..api_envelope import envelope, error_envelope
from .data_ingestion import upload_dataset as _internal_upload_dataset

router = APIRouter(prefix="/api/v1/imports", tags=["universal-import"])
WRITE_ROLES = ("FIRM_ADMIN", "PARTNER", "MANAGER", "SENIOR", "ARTICLE")

# Maps the spec's coarse data_type vocabulary (Section 22) onto this system's
# actual fine-grained dataset_type enum. Where the spec's category is
# genuinely ambiguous (gst, tds — several distinct real datasets exist under
# each), `subtype` disambiguates; a request with no subtype gets a clear
# error listing the valid options rather than silently guessing.
DATA_TYPE_MAP = {
    "trial_balance": {"default": "TRIAL_BALANCE"},
    "general_ledger": {"default": "GENERAL_LEDGER"},
    "sales": {"default": "SALES_REGISTER"},
    "purchase": {"default": "PURCHASE_REGISTER"},
    "bank": {"default": "BANK_STATEMENT"},
    "gst": {"subtypes": {"gstr1": "GSTR1", "gstr2b": "GSTR2B", "gstr3b": "GSTR3B"}},
    "tds": {"subtypes": {"ledger": "TDS_LEDGER", "challan": "TDS_CHALLAN", "return": "TDS_RETURN"}},
    "far": {"default": "FIXED_ASSET_REGISTER"},
    "inventory": {"default": "INVENTORY_REGISTER"},
    "payroll": {"default": "PAYROLL_REGISTER"},
    "loan": {"default": "LOAN_REGISTER"},
    "investment": {"default": "INVESTMENT_REGISTER"},
    "vendor_master": {"default": "VENDOR_MASTER"},
    "customer_master": {"default": "CUSTOMER_MASTER"},
    "employee_master": {"default": "EMPLOYEE_MASTER"},
    "intercompany": {"subtypes": {"ledger": "INTERCOMPANY_LEDGER", "confirmation": "INTERCOMPANY_CONFIRMATION"}},
    # Section 22 also lists 'tax' and 'share_capital' — no ingestion type
    # exists for either yet (Income Tax/AIS ingestion and share capital
    # register ingestion are both real, documented gaps, not silently
    # mapped to something they aren't).
}


def _resolve_dataset_type(data_type: str, subtype: str | None) -> str:
    entry = DATA_TYPE_MAP.get(data_type)
    if entry is None:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            f"data_type '{data_type}' has no ingestion path built yet. "
            f"Supported: {', '.join(sorted(DATA_TYPE_MAP.keys()))}.",
        )
    if "default" in entry:
        return entry["default"]
    subtypes = entry["subtypes"]
    if subtype not in subtypes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"data_type '{data_type}' requires a subtype: {', '.join(sorted(subtypes.keys()))}.",
        )
    return subtypes[subtype]


@router.post("")
async def universal_import(
    engagement_id: UUID = Form(...),
    data_type: str = Form(...),
    subtype: str | None = Form(None),
    source: str = Form("FILE_UPLOAD"),  # Section 22: client/financial_year/data_type/source/file
    on_duplicate: str = Form("ASK"),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    """Genuinely reuses the existing, already-tested upload_dataset logic —
    calling it directly with explicit arguments bypasses only FastAPI's
    HTTP-layer parameter binding (the Form(...)/File(...) defaults), not the
    actual parsing/validation/persistence code, which runs unchanged. This
    is the 'do not create duplicate systems' principle applied literally."""
    if source not in ("FILE_UPLOAD", "MANUAL"):
        return error_envelope(
            "SOURCE_NOT_AVAILABLE",
            f"source='{source}' is not available — no live API is connected for any provider in this build "
            f"(see GET /api/v1/integrations). Use source='FILE_UPLOAD' instead.",
            retryable=False, fallback_available=True,
        )

    dataset_type = _resolve_dataset_type(data_type, subtype)

    result = await _internal_upload_dataset(
        engagement_id=engagement_id, dataset_type=dataset_type, file=file,
        on_duplicate=on_duplicate, user=user,
    )

    # upload_dataset returns either an IngestionSummary or a
    # DuplicateDetectedResponse pydantic model — normalize both into the
    # Section 23 import-batch status vocabulary.
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result
    if result_dict.get("duplicate_detected"):
        return envelope({**result_dict, "import_batch_id": result_dict.get("previous_ingestion_run_id"), "status": "REQUIRES_REVIEW"}, source=source)

    status_map = {
        "COMPLETED": "IMPORTED", "COMPLETED_WITH_WARNINGS": "PARTIALLY_IMPORTED", "FAILED": "FAILED",
    }
    return envelope(
        {
            "import_batch_id": result_dict["ingestion_run_id"],
            "status": status_map.get(result_dict["status"], result_dict["status"]),
            "records_received": result_dict["rows_total"],
            "records_accepted": result_dict["rows_valid"],
            "records_rejected": result_dict["rows_rejected"],
            "data_quality_score": result_dict["data_quality_score"],
        },
        source=source,
    )


@router.get("/{batch_id}")
async def get_import_batch(batch_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        row = await conn.fetchrow(
            """select id, engagement_id, dataset_type, file_name, status, rows_total, rows_valid,
                      rows_rejected, data_quality_score, started_at, completed_at, started_by
               from ingestion_run where id=$1""",
            batch_id,
        )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import batch not found")
    status_map = {"COMPLETED": "IMPORTED", "COMPLETED_WITH_WARNINGS": "PARTIALLY_IMPORTED", "FAILED": "FAILED", "PROCESSING": "PROCESSING"}
    return envelope({
        "import_batch_id": row["id"], "engagement_id": row["engagement_id"], "data_type": row["dataset_type"],
        "file_name": row["file_name"], "status": status_map.get(row["status"], row["status"]),
        "records_received": row["rows_total"], "records_accepted": row["rows_valid"], "records_rejected": row["rows_rejected"],
        "data_quality_score": float(row["data_quality_score"]) if row["data_quality_score"] is not None else None,
        "uploaded_at": row["started_at"].isoformat(), "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
        "uploaded_by": row["started_by"],
    })


@router.get("")
async def list_import_batches(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        rows = await conn.fetch(
            """select id, dataset_type, file_name, status, rows_total, rows_valid, rows_rejected, started_at
               from ingestion_run where engagement_id=$1 order by started_at desc""",
            engagement_id,
        )
    status_map = {"COMPLETED": "IMPORTED", "COMPLETED_WITH_WARNINGS": "PARTIALLY_IMPORTED", "FAILED": "FAILED", "PROCESSING": "PROCESSING"}
    return envelope([
        {
            "import_batch_id": r["id"], "data_type": r["dataset_type"], "file_name": r["file_name"],
            "status": status_map.get(r["status"], r["status"]), "records_received": r["rows_total"],
            "records_accepted": r["rows_valid"], "records_rejected": r["rows_rejected"],
            "uploaded_at": r["started_at"].isoformat(),
        }
        for r in rows
    ])
