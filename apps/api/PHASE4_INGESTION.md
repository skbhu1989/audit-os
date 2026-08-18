# AI Audit OS — Phase 4: Data Ingestion (Excel/CSV → Universal Data Model)

Parses Trial Balance, General Ledger, Vendor Master, and Customer Master
files (Excel or CSV, Tally/Zoho/SAP-style loose column naming) into validated
rows and persists them into the Phase 2 schema. **Every parser and endpoint
here was exercised against real files through the running API** — deliberately
messy ones, not just clean happy-path examples — and four real bugs were
found and fixed as a result.

## Architecture

`app/ingestion.py` is pure Python — pandas DataFrames in, `ParseResult` out —
with no DB or FastAPI dependency, so it's unit-testable on its own and reusable
by a future async worker (per Section CJ: long-running jobs on large files
shouldn't run inline in the request/response cycle — see "Known gaps" below).

`app/routers/data_ingestion.py` wires that into the API: saves the uploaded
file to object storage, calls the right parser for `dataset_type`, records an
`ingestion_run` + per-row `ingestion_exception`s, and — only if the dataset
didn't fail outright — writes the valid rows into `account`/`trial_balance_line`,
`journal`/`journal_line`, or `vendor`/`customer`.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /engagements/{id}/data/upload` | multipart upload; `dataset_type` = TRIAL_BALANCE / GENERAL_LEDGER / VENDOR_MASTER / CUSTOMER_MASTER / SALES_REGISTER / PURCHASE_REGISTER / BANK_STATEMENT |
| `GET /engagements/{id}/data/ingestion-runs` | history of uploads with quality scores |
| `GET /engagements/{id}/data/ingestion-runs/{run_id}/exceptions` | row-level drill-down |
| `GET /engagements/{id}/data/trial-balance` | current TB, for confirming ingestion landed correctly |

## Validation rules implemented (Section N: Data Validation Engine)

- **Trial Balance**: missing ledger name, negative amounts, a line with both
  debit and credit non-zero, both zero (warning), duplicate ledger names
  (warning), and — critically — **the trial balance not tying** (total debit
  ≠ total credit) is a dataset-level error that blocks the *entire* upload
  from being persisted, not just the offending row (there isn't one single
  offending row for a tie-out failure).
- **General Ledger**: unparseable dates, missing/zero/negative amounts,
  missing debit or credit account (unbalanced entry), same account on both
  sides (warning).
- **Vendor/Customer Master**: missing name, malformed GSTIN/PAN (regex-checked,
  warning not error — a bad-format GSTIN might still be a real vendor worth
  investigating, not a reason to silently drop the row), duplicate names
  within the same file (warning).
- **Sales/Purchase Register**: missing invoice number, missing party name,
  unparseable date, missing/negative taxable value, duplicate invoice number
  within the file (warning), stated total not matching taxable value + taxes
  (warning — kept as reported, flagged for investigation rather than silently
  overwritten), malformed GSTIN (warning). Persists to `invoice`, auto-creating
  a stub vendor/customer by name if the party isn't already in the master.
- **Bank Statement**: unparseable date, negative debit/credit, both zero
  (warning — legitimately happens on an opening-balance row, not rejected),
  both non-zero on the same line (warning — possible contra entry), missing
  description (warning). Persists to `bank_transaction` following the schema's
  sign convention: credit (money in) is positive, debit (money out) is negative.
- **Data Quality Score** (0–100): row-level, not issue-level — a row with two
  warning-severity problems still only costs one row's worth of penalty.
  Error rows are weighted 2x a warning row.

## What was actually verified end-to-end

Uploaded through the live API (not just unit-tested in isolation):

1. A clean, tying trial balance → `COMPLETED`, quality score 100, all 20 rows
   land in `trial_balance_line` with matching `account` rows auto-created.
2. A deliberately non-tying trial balance → `FAILED`, and confirmed via direct
   query that **none** of its rows were persisted — the TB read-back after
   both uploads reflects only the clean one.
3. A general ledger with 2 bad rows (unparseable date, zero amount) out of 6
   → correctly rejects exactly those 2 with the right row numbers and
   messages, persists the other 4 as balanced `journal`/`journal_line` pairs
   (verified `SUM(debit) = SUM(credit) = journal.amount` for each, directly
   against the DB).
4. A vendor master with a malformed-GSTIN/PAN row and an upsert-by-name
   collision → warnings raised correctly, existing vendor's blank fields
   filled by `COALESCE` without clobbering already-populated ones.
5. A customer master, clean → 100 score, all rows land.
6. A sales register with a duplicate invoice number and an unparseable date
   → correctly warns on the duplicate, rejects only the bad-date row, and
   auto-creates a stub `customer` record (with GSTIN) for a party not yet in
   any customer master — confirmed directly against the DB, including that
   the *rejected* row's party was correctly **not** created.
7. A purchase register, clean → all three invoices land with `direction =
   PURCHASE` and correctly linked to `vendor_id` (not `customer_id`).
8. A bank statement with an opening-balance row (both debit/credit blank), two
   real transactions, and one unparseable date → the opening-balance row is
   kept (warned, not rejected — it's a legitimate pattern), the bad-date row
   is rejected, and the persisted `amount` sign convention was verified
   directly: credits landed positive, debits negative.

## Bugs found by actually running this (not caught by reading the code)

1. **`journal_line` was wired into the generic audit-trail trigger from
   migration 010, but has no `engagement_id` column** (only `journal_id`) —
   every journal upload 500'd with `record "new" has no field "engagement_id"`.
   Same root cause as the `client`/`engagement` bug from Phase 3, just a
   different table; fixed the same way, with a dedicated trigger function
   that resolves `engagement_id` via `journal_id → journal.engagement_id`.
   See migration `014_fix_journal_line_audit_trigger.sql`.
2. **`json.dumps()` silently emits the non-standard token `NaN`** for pandas'
   NaN-for-missing-cell values. Valid to Python's `json` module, invalid per
   RFC 8259, and Postgres's `jsonb` correctly rejects it — every vendor/
   customer upload with a single blank cell 400'd on the exception-logging
   step. Fixed with `_json_safe_row()`, which converts NaN → `None` before
   serializing.
3. **Traced (not yet triggered, but real) design bug**: the original status
   logic marked a non-tying trial balance as `COMPLETED_WITH_WARNINGS` (since
   `rows_valid > 0`) and would have persisted its individually-valid-looking
   rows anyway — silently writing a known-not-to-tie TB into the schema.
   Fixed by distinguishing dataset-level errors (`row_number == 0`, e.g. the
   tie-out check) from row-level ones: any dataset-level error now forces
   `FAILED` and blocks persistence entirely, verified by test #2 above.
4. Same NaN-truthiness bug class as the earlier `_clean_str` fix (bare
   `str(x or "").strip() or None` returning the literal string `"nan"` for a
   blank cell) was pre-empted here by reusing `_clean_str` throughout rather
   than repeating the pattern — worth calling out since it's an easy mistake
   to reintroduce in future parsers.

## Known gaps / not yet built

- **Synchronous processing.** Upload, parse, and persist all happen inline in
  the request. Fine for the sample-sized files tested here; the Phase 1
  architecture calls for async job processing (queue + worker) once real
  files approach the "millions of transactions" scale — `app/ingestion.py`
  was deliberately kept DB/framework-agnostic so it can be lifted into a
  worker without rewriting the parsing logic.
- **No Tally XML / SAP / Zoho API connectors yet** — only CSV/XLSX with
  flexible column-name matching. Direct Tally XML export parsing and live
  API connectors are separate work.
- **Vendor/customer duplicate detection is exact-name-match only** (after
  basic normalization). The spec's fuzzy-matching duplicate detection
  ("ABC Traders" vs "ABC Trader's Co") is Master Data Consistency Engine
  territory (Section 84) — not built here.
- **No re-upload/versioning UX** — uploading a corrected file creates a new
  `ingestion_run` and a fresh set of `trial_balance_line` rows rather than
  superseding the previous ones; `document.supersedes_document_id` exists in
  the schema for this but isn't wired up on the ingestion side yet.
- **Bank statement, sales register, and purchase register parsers** are now
  built and tested (see above) — Phase 4's four MVP input types (Section 53:
  Trial Balance, GL, Sales Register, Purchase Register, Bank Statement, Vendor
  Master, Customer Master) are all covered.

## Next phase

Phase 5 (TB mapping + GL engine) can now build on real persisted data: FS-line
auto-mapping for the `account` table, and the GL/JE risk-scoring analytics
from the earlier prototype — this time computed from actual uploaded data
rather than synthetic sample data.
