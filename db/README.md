# AI Audit OS — Phase 2: Database Schema

10 ordered PostgreSQL migrations implementing the full Universal Data Model from
the Phase 1 architecture spec (Section 5, ER Model). **Tested end-to-end against
a real PostgreSQL 16 instance** — all 10 files run clean in sequence, producing
50 tables + 1 view, with row-level security and audit-trail triggers verified
to actually work (not just syntactically valid).

## Running it

```bash
createdb audit_os
for f in migrations/*.sql; do psql -d audit_os -v ON_ERROR_STOP=1 -f "$f"; done
```

Files must run in numeric order — each one depends on tables/types created earlier.

## What's in each file

| File | Contents |
|---|---|
| 001_tenancy.sql | Firm, users, clients, engagements, periods, engagement team |
| 002_universal_data_model.sql | Chart of accounts, trial balance, journals/lines, vendor/customer/employee masters |
| 003_transactions.sql | Invoices, credit/debit notes, PO/GRN, payments/receipts, bank transactions |
| 004_statutory.sql | GST/TDS transactions, returns, challans, statutory liability roll-forward, compliance calendar, ageing view |
| 005_assets_capital.sql | Fixed assets, inventory, loans, investments, share capital, related parties |
| 006_documents_evidence.sql | Document storage refs, OCR extraction output, the Evidence Graph edge table |
| 007_audit_engine.sql | Audit procedures, evidence, the central `audit_exception` hub, client queries, working papers |
| 008_reconciliation.sql | Shared reconciliation engine: runs, matches (L1–L6 hierarchy), exceptions |
| 009_rules_and_versioning.sql | Versioned, effective-dated rule engine (TDS rates, materiality, etc.), with seed data |
| 010_audit_trail_and_rls.sql | Append-only audit trail trigger, row-level security policies |

## Key design decisions

**Tenant isolation is enforced at the database layer, not just in application code.**
Every engagement-scoped table has an RLS policy that resolves `engagement_id → client → firm`
and compares against a session variable (`app.current_firm_id`) the API sets per request
(`SET LOCAL app.current_firm_id = '<uuid>'` inside each transaction). Tested: with no
tenant context set, queries return **zero rows** — the system fails closed, not open.

**`audit_exception` is the hub, not GST/TDS-specific tables.** Every reconciliation
mismatch, risky journal entry, or analytics flag ultimately produces a row here, which is
what drives the query register, risk engine, and working papers. Reconciliation-specific
detail (the Section 59 column set: GSTIN, document no., taxable value, CGST/SGST/IGST...)
lives in `reconciliation_exception`, linked via `audit_exception_id`.

**The matching hierarchy (Section AZ/79) is one shared engine**, not duplicated per
statutory type. `reconciliation_run` → `reconciliation_match` (with `match_level` L1–L6,
`confidence_score`, `matching_factors[]`) is used identically by GST, TDS, PF/ESI, MCA,
and bank reconciliation — only `recon_type` and which source tables feed it differ.

**Rules are versioned and effective-dated, never hardcoded.** `rule_version` has a
Postgres `EXCLUDE` constraint (tested) that makes it *structurally impossible* to insert
two overlapping-date versions of the same rule — the database itself enforces "never
apply today's rate to a historical period" (Section BU), rather than relying on
application code to remember.

**Ageing is a view, not a stored column.** `age_days`/`ageing_bucket` depend on
`current_date`, which Postgres correctly refuses inside a `GENERATED ALWAYS` column
(caught this by actually running the migration, not just reading the SQL) — so
`v_statutory_dues_ageing` computes it live instead.

**Documents are references, not blobs.** `document.storage_uri` points to object
storage; Postgres never holds file bytes.

## What was actually verified (not just written)

1. All 10 migrations run in order against Postgres 16 with zero errors.
2. Seeded two separate firms/clients/engagements and confirmed, connected as a
   non-owner `app_runtime` role: Firm A's session sees only Firm A's ledger,
   Firm B's session sees only Firm B's, and a session with no tenant context
   set sees nothing.
3. Confirmed the audit-trail trigger fires and captures a correct before/after
   diff on both INSERT and UPDATE for a table it's attached to (`journal`).

## Known simplifications to revisit before production

- The audit-trail trigger is attached to an explicit table list (10 tables), not
  all 50 — extend the array in `010_audit_trail_and_rls.sql` as more tables prove
  audit-critical.
- `rule.logic` is a loosely-typed `jsonb` blob; a production system should validate
  it against a per-category JSON Schema at write time.
- No partitioning yet on high-volume tables (`journal_line`, `gst_transaction`,
  `bank_transaction`) — add range partitioning by `engagement_id`/period once a
  tenant's volume approaches the millions-of-rows range described in Phase 1's
  scalability section.
- Full-text/fuzzy matching (Section AZ Level 5) needs `pg_trgm` indexes on
  `vendor.name`/`customer.name` — not yet added, since the fuzzy-match thresholds
  should be tuned against real data first.
