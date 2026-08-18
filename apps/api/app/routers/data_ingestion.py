import os
import json
import hashlib
from typing import Union
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, require_roles, CurrentUser
from ..ingestion import (
    load_tabular, parse_trial_balance, parse_journal, parse_party_master,
    parse_invoice_register, parse_bank_statement, parse_gst_return, parse_gstr3b_summary,
    parse_tds_ledger, parse_tds_challan, parse_tds_return, parse_employee_master, parse_payroll_register,
    parse_fixed_asset_register, parse_inventory_register, parse_loan_register, parse_investment_register,
    parse_intercompany_transactions,
    ParseResult,
)

router = APIRouter(prefix="/engagements/{engagement_id}/data", tags=["data-ingestion"])

WRITE_ROLES = ("FIRM_ADMIN", "PARTNER", "MANAGER", "SENIOR", "ARTICLE")  # data upload is fieldwork, not just management

# Object storage stub: in production this is S3/GCS; document.storage_uri stores
# a URI either way, so swapping this out later doesn't touch the schema.
STORAGE_ROOT = os.environ.get("STORAGE_ROOT", "/home/claude/objectstore")


def _save_to_storage(engagement_id: str, filename: str, content: bytes) -> str:
    folder = os.path.join(STORAGE_ROOT, engagement_id)
    os.makedirs(folder, exist_ok=True)
    unique_name = f"{uuid4()}_{filename}"
    path = os.path.join(folder, unique_name)
    with open(path, "wb") as f:
        f.write(content)
    return f"file://{path}"


class IngestionSummary(BaseModel):
    ingestion_run_id: UUID
    status: str
    rows_total: int
    rows_valid: int
    rows_rejected: int
    data_quality_score: float
    error_count: int
    warning_count: int


class DuplicateDetectedResponse(BaseModel):
    duplicate_detected: bool
    previous_ingestion_run_id: UUID
    previous_uploaded_at: str
    message: str


# Tables safe to wipe-and-replace on REPLACE: each is written by exactly one
# dataset type via plain INSERT (no upsert), so replacing means "delete
# everything this dataset type previously contributed, then re-insert."
# Master-data types (VENDOR_MASTER/CUSTOMER_MASTER/EMPLOYEE_MASTER) are
# deliberately excluded — their persistence already upserts by name/code,
# so duplicate uploads are naturally idempotent and a destructive delete
# would risk breaking foreign keys from stub records other dataset types
# create (e.g. a stub vendor auto-created by a purchase register upload).
async def _replace_prior_data(conn, engagement_id, dataset_type):
    if dataset_type == "TRIAL_BALANCE":
        await conn.execute("delete from trial_balance_line where engagement_id=$1", engagement_id)
    elif dataset_type == "GENERAL_LEDGER":
        await conn.execute("delete from journal where engagement_id=$1", engagement_id)  # cascades to journal_line
    elif dataset_type == "BANK_STATEMENT":
        await conn.execute("delete from bank_transaction where engagement_id=$1", engagement_id)
    elif dataset_type in ("GSTR1", "GSTR2B"):
        await conn.execute("delete from gst_transaction where engagement_id=$1 and source=$2", engagement_id, dataset_type)
    elif dataset_type == "GSTR3B":
        await conn.execute("delete from gst_transaction where engagement_id=$1 and source='GSTR3B'", engagement_id)
    elif dataset_type == "TDS_LEDGER":
        await conn.execute("delete from tds_transaction where engagement_id=$1 and source='LEDGER'", engagement_id)
    elif dataset_type == "TDS_RETURN":
        await conn.execute("delete from tds_transaction where engagement_id=$1 and source='RETURN'", engagement_id)
    elif dataset_type == "TDS_CHALLAN":
        await conn.execute("delete from challan where engagement_id=$1 and statutory_type='TDS'", engagement_id)
    elif dataset_type in ("PF_CHALLAN", "ESI_CHALLAN", "PT_CHALLAN"):
        scheme = dataset_type.split("_")[0]
        await conn.execute("delete from challan where engagement_id=$1 and statutory_type=$2", engagement_id, scheme)
    elif dataset_type == "PAYROLL_REGISTER":
        await conn.execute("delete from payroll_line where engagement_id=$1", engagement_id)
    elif dataset_type in ("SALES_REGISTER", "PURCHASE_REGISTER"):
        direction = "SALES" if dataset_type == "SALES_REGISTER" else "PURCHASE"
        await conn.execute("delete from invoice where engagement_id=$1 and direction=$2", engagement_id, direction)
    elif dataset_type == "FIXED_ASSET_REGISTER":
        await conn.execute("delete from fixed_asset where engagement_id=$1", engagement_id)
    elif dataset_type == "INVENTORY_REGISTER":
        await conn.execute("delete from inventory_item where engagement_id=$1", engagement_id)
    elif dataset_type == "LOAN_REGISTER":
        await conn.execute("delete from loan where engagement_id=$1", engagement_id)
    elif dataset_type == "INVESTMENT_REGISTER":
        await conn.execute("delete from investment where engagement_id=$1", engagement_id)
    elif dataset_type in ("INTERCOMPANY_LEDGER", "INTERCOMPANY_CONFIRMATION"):
        source = "BOOKS" if dataset_type == "INTERCOMPANY_LEDGER" else "CONFIRMATION"
        await conn.execute("delete from intercompany_transaction where engagement_id=$1 and source=$2", engagement_id, source)
    # VENDOR_MASTER / CUSTOMER_MASTER / EMPLOYEE_MASTER: no-op, upsert handles it


DATASET_DOC_CATEGORY = {
    "TRIAL_BALANCE": "OTHER",
    "GENERAL_LEDGER": "OTHER",
    "VENDOR_MASTER": "OTHER",
    "CUSTOMER_MASTER": "OTHER",
    "SALES_REGISTER": "OTHER",
    "PURCHASE_REGISTER": "OTHER",
    "BANK_STATEMENT": "BANK_STATEMENT",
    "GSTR1": "RETURN_FILING",
    "GSTR2B": "RETURN_FILING",
    "GSTR3B": "RETURN_FILING",
    "TDS_LEDGER": "OTHER",
    "TDS_CHALLAN": "CHALLAN",
    "TDS_RETURN": "RETURN_FILING",
    "EMPLOYEE_MASTER": "OTHER",
    "PAYROLL_REGISTER": "OTHER",
    "PF_CHALLAN": "CHALLAN",
    "ESI_CHALLAN": "CHALLAN",
    "PT_CHALLAN": "CHALLAN",
    "FIXED_ASSET_REGISTER": "OTHER",
    "INVENTORY_REGISTER": "OTHER",
    "LOAN_REGISTER": "OTHER",
    "INVESTMENT_REGISTER": "OTHER",
    "INTERCOMPANY_LEDGER": "OTHER",
    "INTERCOMPANY_CONFIRMATION": "OTHER",
}


from typing import Union
@router.post("/upload", response_model=Union[IngestionSummary, DuplicateDetectedResponse], status_code=201)
async def upload_dataset(
    engagement_id: UUID,
    dataset_type: str = Form(...),
    file: UploadFile = File(...),
    on_duplicate: str = Form("ASK"),  # 'ASK' | 'REPLACE' | 'APPEND' | 'CANCEL' — Section 41
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    if dataset_type not in DATASET_DOC_CATEGORY:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown dataset_type '{dataset_type}'")

    content = await file.read()
    content_hash = hashlib.sha256(content).hexdigest()

    # Section 41: detect a re-upload of the exact same file before doing
    # anything else. Discovered this was missing by accidentally duplicating
    # 17 datasets' worth of real engagement data while testing the Pre-Audit
    # dashboard — every downstream number (bank reconciliation, challan
    # mapping) was silently wrong until traced back to this root cause.
    async with tenant_conn(user.firm_id) as conn:
        existing = await conn.fetchrow(
            """select id, started_at, rows_valid from ingestion_run
               where engagement_id=$1 and dataset_type=$2 and content_hash=$3
               order by started_at desc limit 1""",
            engagement_id, dataset_type, content_hash,
        )
    if existing and on_duplicate == "ASK":
        return DuplicateDetectedResponse(
            duplicate_detected=True,
            previous_ingestion_run_id=existing["id"],
            previous_uploaded_at=existing["started_at"].isoformat(),
            message=(
                f"An identical file was already uploaded for {dataset_type} on "
                f"{existing['started_at'].date()} ({existing['rows_valid']} rows). "
                f"Resubmit with on_duplicate=REPLACE to supersede it, APPEND to load it "
                f"again anyway, or CANCEL to do nothing."
            ),
        )
    if existing and on_duplicate == "CANCEL":
        return DuplicateDetectedResponse(
            duplicate_detected=True, previous_ingestion_run_id=existing["id"],
            previous_uploaded_at=existing["started_at"].isoformat(), message="Upload cancelled — no changes made.",
        )

    try:
        df = load_tabular(content, file.filename)
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not read file as CSV/Excel: {e}")

    if dataset_type == "TRIAL_BALANCE":
        result = parse_trial_balance(df)
    elif dataset_type == "GENERAL_LEDGER":
        result = parse_journal(df)
    elif dataset_type == "VENDOR_MASTER":
        result = parse_party_master(df, "vendor")
    elif dataset_type == "CUSTOMER_MASTER":
        result = parse_party_master(df, "customer")
    elif dataset_type in ("SALES_REGISTER", "PURCHASE_REGISTER"):
        result = parse_invoice_register(df, "SALES" if dataset_type == "SALES_REGISTER" else "PURCHASE")
    elif dataset_type == "BANK_STATEMENT":
        result = parse_bank_statement(df)
    elif dataset_type in ("GSTR1", "GSTR2B"):
        result = parse_gst_return(df, dataset_type)
    elif dataset_type == "GSTR3B":
        result = parse_gstr3b_summary(df)
    elif dataset_type == "TDS_LEDGER":
        result = parse_tds_ledger(df)
    elif dataset_type == "TDS_CHALLAN":
        result = parse_tds_challan(df)
    elif dataset_type == "TDS_RETURN":
        result = parse_tds_return(df)
    elif dataset_type == "EMPLOYEE_MASTER":
        result = parse_employee_master(df)
    elif dataset_type == "PAYROLL_REGISTER":
        result = parse_payroll_register(df)
    elif dataset_type in ("PF_CHALLAN", "ESI_CHALLAN", "PT_CHALLAN"):
        result = parse_tds_challan(df)  # identical shape: section/challan_no/bsr_code/date/amount
    elif dataset_type == "FIXED_ASSET_REGISTER":
        result = parse_fixed_asset_register(df)
    elif dataset_type == "INVENTORY_REGISTER":
        result = parse_inventory_register(df)
    elif dataset_type == "LOAN_REGISTER":
        result = parse_loan_register(df)
    elif dataset_type == "INVESTMENT_REGISTER":
        result = parse_investment_register(df)
    elif dataset_type in ("INTERCOMPANY_LEDGER", "INTERCOMPANY_CONFIRMATION"):
        result = parse_intercompany_transactions(df)
    else:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, f"Parser for '{dataset_type}' not yet built")

    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id = $1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        storage_uri = _save_to_storage(str(engagement_id), file.filename, content)
        doc = await conn.fetchrow(
            """insert into document (engagement_id, category, file_name, storage_uri, uploaded_by)
               values ($1, $2, $3, $4, $5) returning id""",
            engagement_id, DATASET_DOC_CATEGORY[dataset_type], file.filename, storage_uri, user.user_id,
        )
        document_id = doc["id"]

        error_count = sum(1 for i in result.issues if i.severity == "ERROR")
        warning_count = sum(1 for i in result.issues if i.severity == "WARNING")
        # Global-level errors (row_number == 0, e.g. missing columns or a trial
        # balance that doesn't tie) are a reason to withhold the WHOLE dataset,
        # not just skip the offending row — there is no single offending row.
        # Caught by tracing this logic before testing: a non-tying TB with only
        # per-row-valid lines would otherwise still get silently persisted.
        has_global_error = any(i.row_number == 0 and i.severity == "ERROR" for i in result.issues)
        if result.rows_valid == 0 and result.rows_total > 0:
            status_val = "FAILED"
        elif has_global_error:
            status_val = "FAILED"
        elif result.issues:
            status_val = "COMPLETED_WITH_WARNINGS"
        else:
            status_val = "COMPLETED"

        run = await conn.fetchrow(
            """insert into ingestion_run (engagement_id, document_id, dataset_type, file_name,
                                            status, rows_total, rows_valid, rows_rejected,
                                            data_quality_score, completed_at, started_by, content_hash)
               values ($1,$2,$3,$4,$5,$6,$7,$8,$9, now(), $10, $11)
               returning id""",
            engagement_id, document_id, dataset_type, file.filename,
            status_val, result.rows_total, result.rows_valid, result.rows_rejected,
            result.quality_score(), user.user_id, content_hash,
        )
        run_id = run["id"]

        for issue in result.issues:
            await conn.execute(
                """insert into ingestion_exception (ingestion_run_id, row_number, field, message, severity, raw_row)
                   values ($1,$2,$3,$4,$5,$6)""",
                run_id, issue.row_number, issue.field, issue.message, issue.severity,
                json.dumps(issue.raw_row, default=str),
            )

        # Persist valid rows into the Universal Data Model — only if the
        # dataset didn't fail outright (e.g. an unbalanced/non-tying TB isn't
        # written half-finished; the auditor fixes the source file and
        # re-uploads rather than working from a known-bad trial balance).
        if status_val != "FAILED":
            if on_duplicate == "REPLACE" and existing:
                await _replace_prior_data(conn, engagement_id, dataset_type)
            if dataset_type == "TRIAL_BALANCE":
                await _persist_trial_balance(conn, engagement_id, result.valid_rows, run_id)
            elif dataset_type == "GENERAL_LEDGER":
                await _persist_journal(conn, engagement_id, result.valid_rows, run_id)
            elif dataset_type == "VENDOR_MASTER":
                await _persist_parties(conn, engagement_id, result.valid_rows, run_id, "vendor")
            elif dataset_type == "CUSTOMER_MASTER":
                await _persist_parties(conn, engagement_id, result.valid_rows, run_id, "customer")
            elif dataset_type in ("SALES_REGISTER", "PURCHASE_REGISTER"):
                await _persist_invoice_register(conn, engagement_id, result.valid_rows, run_id)
            elif dataset_type == "BANK_STATEMENT":
                await _persist_bank_statement(conn, engagement_id, result.valid_rows, run_id)
            elif dataset_type in ("GSTR1", "GSTR2B"):
                await _persist_gst_return(conn, engagement_id, dataset_type, result.valid_rows, run_id)
            elif dataset_type == "GSTR3B":
                await _persist_gstr3b_summary(conn, engagement_id, result.valid_rows, run_id)
            elif dataset_type == "TDS_LEDGER":
                await _persist_tds_ledger(conn, engagement_id, result.valid_rows, run_id)
            elif dataset_type == "TDS_CHALLAN":
                await _persist_tds_challan(conn, engagement_id, result.valid_rows, run_id)
            elif dataset_type == "TDS_RETURN":
                await _persist_tds_return(conn, engagement_id, result.valid_rows, run_id)
            elif dataset_type == "EMPLOYEE_MASTER":
                await _persist_employee_master(conn, engagement_id, result.valid_rows, run_id)
            elif dataset_type == "PAYROLL_REGISTER":
                await _persist_payroll_register(conn, engagement_id, result.valid_rows, run_id)
            elif dataset_type in ("PF_CHALLAN", "ESI_CHALLAN", "PT_CHALLAN"):
                scheme = dataset_type.split("_")[0]  # 'PF' / 'ESI' / 'PT'
                await _persist_statutory_challan(conn, engagement_id, scheme, result.valid_rows, run_id)
            elif dataset_type == "FIXED_ASSET_REGISTER":
                await _persist_fixed_asset_register(conn, engagement_id, result.valid_rows, run_id)
            elif dataset_type == "INVENTORY_REGISTER":
                await _persist_inventory_register(conn, engagement_id, result.valid_rows, run_id)
            elif dataset_type == "LOAN_REGISTER":
                await _persist_loan_register(conn, engagement_id, result.valid_rows, run_id)
            elif dataset_type == "INVESTMENT_REGISTER":
                await _persist_investment_register(conn, engagement_id, result.valid_rows, run_id)
            elif dataset_type in ("INTERCOMPANY_LEDGER", "INTERCOMPANY_CONFIRMATION"):
                source = "BOOKS" if dataset_type == "INTERCOMPANY_LEDGER" else "CONFIRMATION"
                await _persist_intercompany(conn, engagement_id, source, result.valid_rows, run_id)

        # Data Centre coverage tracking (Section 17/39): this dataset/period's
        # coverage status is updated regardless of whether the run FAILED —
        # a failed upload still means "something was uploaded and it had a
        # problem," which is a different, more informative state than
        # NOT_UPLOADED. Only a genuinely empty file leaves coverage untouched.
        from ..data_centre import coverage_status
        cov_period = _infer_period(dataset_type, result.valid_rows) or "ALL"
        cov_status = coverage_status(result.rows_valid, result.rows_rejected) if status_val != "FAILED" else "PARTIAL"
        await conn.execute(
            """insert into data_coverage (engagement_id, dataset_type, period, status, latest_ingestion_run_id, updated_at)
               values ($1,$2,$3,$4,$5,now())
               on conflict (engagement_id, dataset_type, period) do update set
                 status = excluded.status, latest_ingestion_run_id = excluded.latest_ingestion_run_id, updated_at = now()""",
            engagement_id, dataset_type, cov_period, cov_status, run_id,
        )

    return IngestionSummary(
        ingestion_run_id=run_id, status=status_val,
        rows_total=result.rows_total, rows_valid=result.rows_valid, rows_rejected=result.rows_rejected,
        data_quality_score=result.quality_score(), error_count=error_count, warning_count=warning_count,
    )


def _infer_period(dataset_type: str, valid_rows: list[dict]) -> str | None:
    """Coverage is tracked per period where the dataset has one; datasets
    that are inherently whole-of-engagement (trial balance, masters) use
    the sentinel period 'ALL' rather than a fabricated month."""
    if not valid_rows:
        return None
    if dataset_type == "GENERAL_LEDGER":
        dates = [r.get("posted_date") for r in valid_rows if r.get("posted_date")]
        return dates[0].strftime("%b-%Y") if dates else None
    if dataset_type in ("SALES_REGISTER", "PURCHASE_REGISTER", "GSTR1", "GSTR2B"):
        dates = [r.get("invoice_date") for r in valid_rows if r.get("invoice_date")]
        return dates[0].strftime("%b-%Y") if dates else None
    if dataset_type == "GSTR3B":
        return valid_rows[0].get("period")
    if dataset_type == "PAYROLL_REGISTER":
        return valid_rows[0].get("period")
    if dataset_type == "BANK_STATEMENT":
        dates = [r.get("txn_date") for r in valid_rows if r.get("txn_date")]
        return dates[0].strftime("%b-%Y") if dates else None
    return None


async def _persist_trial_balance(conn, engagement_id, rows, run_id):
    for r in rows:
        acc = await conn.fetchrow(
            "select id from account where engagement_id = $1 and ledger_name = $2",
            engagement_id, r["ledger_name"],
        )
        if not acc:
            acc = await conn.fetchrow(
                "insert into account (engagement_id, ledger_name) values ($1, $2) returning id",
                engagement_id, r["ledger_name"],
            )
        await conn.execute(
            """insert into trial_balance_line (engagement_id, account_id, as_of_date, debit, credit, ingestion_run_id)
               values ($1,$2, current_date, $3, $4, $5)""",
            engagement_id, acc["id"], r["debit"], r["credit"], run_id,
        )


async def _get_or_create_account(conn, engagement_id, ledger_name):
    acc = await conn.fetchrow(
        "select id from account where engagement_id = $1 and ledger_name = $2", engagement_id, ledger_name
    )
    if acc:
        return acc["id"]
    acc = await conn.fetchrow(
        "insert into account (engagement_id, ledger_name) values ($1, $2) returning id", engagement_id, ledger_name
    )
    return acc["id"]


async def _persist_journal(conn, engagement_id, rows, run_id):
    for r in rows:
        journal = await conn.fetchrow(
            """insert into journal (engagement_id, journal_no, posted_date, posted_by, narration, amount, ingestion_run_id)
               values ($1,$2,$3,$4,$5,$6,$7) returning id""",
            engagement_id, r["journal_no"], r["posted_date"], r["posted_by"],
            r["narration"], r["amount"], run_id,
        )
        dr_id = await _get_or_create_account(conn, engagement_id, r["debit_account"])
        cr_id = await _get_or_create_account(conn, engagement_id, r["credit_account"])
        await conn.execute(
            "insert into journal_line (journal_id, account_id, debit, credit) values ($1,$2,$3,0)",
            journal["id"], dr_id, r["amount"],
        )
        await conn.execute(
            "insert into journal_line (journal_id, account_id, debit, credit) values ($1,$2,0,$3)",
            journal["id"], cr_id, r["amount"],
        )


async def _persist_parties(conn, engagement_id, rows, run_id, kind):
    table = "vendor" if kind == "vendor" else "customer"
    for r in rows:
        existing = await conn.fetchrow(
            f"select id from {table} where engagement_id = $1 and lower(name) = lower($2)",
            engagement_id, r["name"],
        )
        bank_account = r.get("bank_account")  # only ever present for vendor rows — parse_party_master
                                                 # only populates this for kind='vendor' (customer has no such column)
        if existing:
            if kind == "vendor":
                await conn.execute(
                    "update vendor set gstin = coalesce($1, gstin), pan = coalesce($2, pan), "
                    "address = coalesce($3, address), bank_account_masked = coalesce($4, bank_account_masked) where id = $5",
                    r["gstin"], r["pan"], r["address"], bank_account, existing["id"],
                )
            else:
                await conn.execute(
                    "update customer set gstin = coalesce($1, gstin), pan = coalesce($2, pan), "
                    "address = coalesce($3, address) where id = $4",
                    r["gstin"], r["pan"], r["address"], existing["id"],
                )
        else:
            if kind == "vendor":
                await conn.execute(
                    """insert into vendor (engagement_id, name, gstin, pan, address, bank_account_masked, ingestion_run_id)
                       values ($1,$2,$3,$4,$5,$6,$7)""",
                    engagement_id, r["name"], r["gstin"], r["pan"], r["address"], bank_account, run_id,
                )
            else:
                await conn.execute(
                    """insert into customer (engagement_id, name, gstin, pan, address, ingestion_run_id)
                       values ($1,$2,$3,$4,$5,$6)""",
                    engagement_id, r["name"], r["gstin"], r["pan"], r["address"], run_id,
                )


async def _get_or_create_party(conn, engagement_id, name, gstin, direction):
    """direction 'SALES' -> customer, 'PURCHASE' -> vendor. Registers often
    reference parties not yet in the master file (or uploaded in a different
    order), so invoice ingestion creates a stub party record rather than
    failing — the vendor/customer master upload later enriches it via the
    same name-match upsert used in _persist_parties."""
    table = "customer" if direction == "SALES" else "vendor"
    existing = await conn.fetchrow(
        f"select id from {table} where engagement_id = $1 and lower(name) = lower($2)", engagement_id, name
    )
    if existing:
        if gstin:
            await conn.execute(f"update {table} set gstin = coalesce(gstin, $1) where id = $2", gstin, existing["id"])
        return existing["id"]
    row = await conn.fetchrow(
        f"insert into {table} (engagement_id, name, gstin) values ($1,$2,$3) returning id",
        engagement_id, name, gstin,
    )
    return row["id"]


async def _persist_invoice_register(conn, engagement_id, rows, run_id):
    for r in rows:
        party_id = await _get_or_create_party(conn, engagement_id, r["party_name"], r["gstin"], r["direction"])
        vendor_id = party_id if r["direction"] == "PURCHASE" else None
        customer_id = party_id if r["direction"] == "SALES" else None
        await conn.execute(
            """insert into invoice (engagement_id, direction, invoice_no, invoice_date, vendor_id, customer_id,
                                      taxable_value, cgst, sgst, igst, cess, total_value)
               values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)""",
            engagement_id, r["direction"], r["invoice_no"], r["invoice_date"], vendor_id, customer_id,
            r["taxable_value"], r["cgst"], r["sgst"], r["igst"], r["cess"], r["total_value"],
        )


async def _persist_bank_statement(conn, engagement_id, rows, run_id):
    for r in rows:
        await conn.execute(
            """insert into bank_transaction (engagement_id, txn_date, description, amount, balance_after)
               values ($1,$2,$3,$4,$5)""",
            engagement_id, r["txn_date"], r["description"], r["amount"], r["balance_after"],
        )


def _period_label(d) -> str:
    return d.strftime("%b-%Y")  # e.g. 'Apr-2025' — matches the format used across the reconciliation engine


async def _persist_gst_return(conn, engagement_id, source, rows, run_id):
    for r in rows:
        await conn.execute(
            """insert into gst_transaction (engagement_id, source, period, gstin, document_no, document_date,
                                              party_name, taxable_value, cgst, sgst, igst, cess)
               values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)""",
            engagement_id, source, _period_label(r["invoice_date"]), r["gstin"], r["invoice_no"], r["invoice_date"],
            r["party_name"], r["taxable_value"], r["cgst"], r["sgst"], r["igst"], r["cess"],
        )


async def _persist_gstr3b_summary(conn, engagement_id, rows, run_id):
    for r in rows:
        await conn.execute(
            """insert into gst_transaction (engagement_id, source, period, taxable_value, cgst, sgst, igst, cess)
               values ($1,'GSTR3B',$2,$3,$4,$5,$6,$7)""",
            engagement_id, r["period"], r["taxable_value"], r["cgst"], r["sgst"], r["igst"], r["cess"],
        )
        import json as _json
        await conn.execute(
            """insert into return_filing (engagement_id, statutory_type, return_code, period, raw_payload)
               values ($1,'GST','GSTR3B',$2,$3)
               on conflict (engagement_id, statutory_type, return_code, period) do update set raw_payload = excluded.raw_payload""",
            engagement_id, r["period"], _json.dumps(r),
        )


async def _persist_tds_ledger(conn, engagement_id, rows, run_id):
    for r in rows:
        await conn.execute(
            """insert into tds_transaction (engagement_id, source, section, deductee_pan, deductee_name,
                                              amount_paid_credited, tds_amount, deduction_date)
               values ($1,'LEDGER',$2,$3,$4,$5,$6,$7)""",
            engagement_id, r["section"], r["deductee_pan"], r["deductee_name"],
            r["amount_paid_credited"], r["tds_amount"], r["deduction_date"],
        )


async def _persist_tds_challan(conn, engagement_id, rows, run_id):
    for r in rows:
        await conn.execute(
            """insert into challan (engagement_id, statutory_type, challan_no, bsr_code, challan_date, amount, tax_head)
               values ($1,'TDS',$2,$3,$4,$5,$6)""",
            engagement_id, r["challan_no"], r["bsr_code"], r["challan_date"], r["amount"], r["section"],
        )


async def _persist_tds_return(conn, engagement_id, rows, run_id):
    for r in rows:
        await conn.execute(
            """insert into tds_transaction (engagement_id, source, section, deductee_pan, tds_amount, quarter)
               values ($1,'RETURN',$2,$3,$4,$5)""",
            engagement_id, r["section"], r["deductee_pan"], r["tds_amount"], r["quarter"],
        )


async def _persist_employee_master(conn, engagement_id, rows, run_id):
    for r in rows:
        if r["employee_code"]:
            existing = await conn.fetchrow(
                "select id from employee where engagement_id=$1 and employee_code=$2", engagement_id, r["employee_code"]
            )
        else:
            existing = None
        if existing:
            await conn.execute(
                "update employee set name=$1, pan=coalesce($2,pan), uan=coalesce($3,uan), "
                "date_of_joining=coalesce($4,date_of_joining) where id=$5",
                r["name"], r["pan"], r["uan"], r["date_of_joining"], existing["id"],
            )
        else:
            await conn.execute(
                """insert into employee (engagement_id, employee_code, name, pan, uan, date_of_joining)
                   values ($1,$2,$3,$4,$5,$6)""",
                engagement_id, r["employee_code"], r["name"], r["pan"], r["uan"], r["date_of_joining"],
            )


async def _get_or_create_employee(conn, engagement_id, employee_code):
    existing = await conn.fetchrow(
        "select id from employee where engagement_id=$1 and employee_code=$2", engagement_id, employee_code
    )
    if existing:
        return existing["id"]
    row = await conn.fetchrow(
        "insert into employee (engagement_id, employee_code, name) values ($1,$2,$3) returning id",
        engagement_id, employee_code, f"(unresolved — code {employee_code})",
    )
    return row["id"]


async def _persist_payroll_register(conn, engagement_id, rows, run_id):
    for r in rows:
        employee_id = await _get_or_create_employee(conn, engagement_id, r["employee_code"])
        await conn.execute(
            """insert into payroll_line (engagement_id, employee_id, period, gross_salary,
                                           pf_employee, pf_employer, esi_employee, esi_employer, pt_amount,
                                           ingestion_run_id)
               values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
            engagement_id, employee_id, r["period"], r["gross_salary"],
            r["pf_employee"], r["pf_employer"], r["esi_employee"], r["esi_employer"], r["pt_amount"], run_id,
        )


async def _persist_statutory_challan(conn, engagement_id, scheme, rows, run_id):
    for r in rows:
        await conn.execute(
            """insert into challan (engagement_id, statutory_type, challan_no, bsr_code, challan_date, amount, tax_head)
               values ($1,$2,$3,$4,$5,$6,$7)""",
            engagement_id, scheme, r["challan_no"], r["bsr_code"], r["challan_date"], r["amount"], r["section"],
        )


async def _persist_fixed_asset_register(conn, engagement_id, rows, run_id):
    for r in rows:
        await conn.execute(
            """insert into fixed_asset (engagement_id, asset_code, description, category, acquisition_date,
                                          gross_block, accum_depreciation, useful_life_years, depreciation_method,
                                          disposal_date, disposal_proceeds, ingestion_run_id)
               values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)""",
            engagement_id, r["asset_code"], r["description"], r["category"], r["acquisition_date"],
            r["gross_block"], r["accum_depreciation"], r["useful_life_years"], r["depreciation_method"],
            r["disposal_date"], r["disposal_proceeds"], run_id,
        )


async def _persist_inventory_register(conn, engagement_id, rows, run_id):
    for r in rows:
        await conn.execute(
            """insert into inventory_item (engagement_id, item_code, description, quantity_on_hand,
                                             unit_cost, nrv, ageing_days, ingestion_run_id)
               values ($1,$2,$3,$4,$5,$6,$7,$8)""",
            engagement_id, r["item_code"], r["description"], r["quantity_on_hand"],
            r["unit_cost"], r["nrv"], r["ageing_days"], run_id,
        )


async def _persist_loan_register(conn, engagement_id, rows, run_id):
    for r in rows:
        await conn.execute(
            """insert into loan (engagement_id, lender_or_borrower, direction, principal_amount,
                                   interest_rate, start_date, maturity_date, outstanding_balance, ingestion_run_id)
               values ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
            engagement_id, r["lender_or_borrower"], r["direction"], r["principal_amount"],
            r["interest_rate"], r["start_date"], r["maturity_date"], r["outstanding_balance"], run_id,
        )


async def _persist_investment_register(conn, engagement_id, rows, run_id):
    for r in rows:
        await conn.execute(
            """insert into investment (engagement_id, investee_name, investment_type, classification,
                                         cost, fair_value, fair_value_date, ingestion_run_id)
               values ($1,$2,$3,$4,$5,$6,$7,$8)""",
            engagement_id, r["investee_name"], r["investment_type"], r["classification"],
            r["cost"], r["fair_value"], r["fair_value_date"], run_id,
        )


async def _persist_intercompany(conn, engagement_id, source, rows, run_id):
    for r in rows:
        await conn.execute(
            """insert into intercompany_transaction (engagement_id, source, counterparty_name, transaction_type,
                                                        transaction_date, amount, currency, reference_no, ingestion_run_id)
               values ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
            engagement_id, source, r["counterparty_name"], r["transaction_type"],
            r["transaction_date"], r["amount"], r["currency"], r["reference_no"], run_id,
        )


class IngestionRunOut(BaseModel):
    id: UUID
    dataset_type: str
    file_name: str
    status: str
    rows_total: int
    rows_valid: int
    rows_rejected: int
    data_quality_score: float | None


@router.get("/ingestion-runs", response_model=list[IngestionRunOut])
async def list_ingestion_runs(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        rows = await conn.fetch(
            """select id, dataset_type, file_name, status, rows_total, rows_valid,
                      rows_rejected, data_quality_score
               from ingestion_run where engagement_id = $1 order by started_at desc""",
            engagement_id,
        )
    return [IngestionRunOut(**dict(r)) for r in rows]


class IngestionExceptionOut(BaseModel):
    row_number: int | None
    field: str | None
    message: str
    severity: str


@router.get("/ingestion-runs/{run_id}/exceptions", response_model=list[IngestionExceptionOut])
async def get_ingestion_exceptions(
    engagement_id: UUID, run_id: UUID, user: CurrentUser = Depends(get_current_user)
):
    async with tenant_conn(user.firm_id) as conn:
        rows = await conn.fetch(
            """select row_number, field, message, severity from ingestion_exception
               where ingestion_run_id = $1 order by row_number""",
            run_id,
        )
    return [IngestionExceptionOut(**dict(r)) for r in rows]


class TrialBalanceLineOut(BaseModel):
    ledger_name: str
    fs_line: str | None
    debit: float
    credit: float
    flag: str | None


@router.get("/trial-balance", response_model=list[TrialBalanceLineOut])
async def get_trial_balance(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    """Latest TB line per ledger — lets the caller confirm ingestion actually
    landed correctly without needing direct DB access."""
    async with tenant_conn(user.firm_id) as conn:
        rows = await conn.fetch(
            """select distinct on (a.id) a.ledger_name, a.fs_line, t.debit, t.credit, t.flag
               from trial_balance_line t join account a on a.id = t.account_id
               where t.engagement_id = $1
               order by a.id, t.as_of_date desc, t.created_at desc""",
            engagement_id,
        )
    return [TrialBalanceLineOut(**dict(r)) for r in rows]
