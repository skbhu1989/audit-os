# AI Finance Control / Pre-Audit Module

Extends the existing Audit Module (Phases 1–12) per the new master prompt,
reusing its data model, auth, and reconciliation engine rather than building
a second disconnected application — exactly as Section "IMPORTANT — EXISTING
APPLICATION" required. Every module below shares the same `engagement`,
`invoice`, `bank_transaction`, `challan`, and reconciliation tables the
Audit Module already writes to.

## What's implemented

| Module | Section | Endpoint(s) |
|---|---|---|
| Data Centre + Dynamic Checklist | 17-18 | `GET /engagements/{id}/data-centre` |
| Books Health Score | 58 | folded into Pre-Audit Dashboard |
| Pre-Audit Dashboard | 129 | `GET /engagements/{id}/pre-audit` |
| Upload Duplicate Detection | 41 | `POST /engagements/{id}/data/upload` (now takes `on_duplicate`) |
| GST/TDS/PF/ESI/PT Challan Mapping | 24, 26 | `GET /engagements/{id}/challan-mapping?statutory_type=X` |
| Bank Reconciliation | 54 | `GET /engagements/{id}/bank-reconciliation` |
| AP Duplicate Invoices + Ageing | 55 | `GET /engagements/{id}/ap/duplicate-invoices`, `/ap/ageing` |
| AR Ageing | 56 | `GET /engagements/{id}/ar/ageing` |
| Month-End Close | 59 | `POST/GET /engagements/{id}/month-end-close` |
| Root Cause Analysis | 61 | `GET /engagements/{id}/exceptions/{id}/root-cause` |
| Exception Management | 60 | `GET/PATCH /engagements/{id}/exceptions`, `POST .../sync` |
| Management Query Engine | 62 | `POST .../draft-query`, `GET/PATCH .../queries` |
| Universal Reconciliation Control Tower | 51 (signature feature) | `GET /engagements/{id}/control-tower` |

## Section 39's core distinction, actually implemented

"DATA GAP" vs "RECONCILIATION EXCEPTION" is enforced at the schema level, not
just in prose: `data_coverage.status` (`NOT_UPLOADED`/`PARTIAL`/`UPLOADED`)
is a completely separate concept from `reconciliation_exception` — an
engagement with zero GST uploads shows `NOT_UPLOADED` on the Data Centre and
contributes zero rows to any exception count. Verified live: before any
upload, coverage is 0%; after uploading a file with some rejected rows,
coverage is `PARTIAL`; a reconciliation exception only exists once real data
was uploaded and didn't tie.

## What was actually verified end-to-end

Everything below was tested against the real Meridian Fashions engagement,
with expected values cross-checked against numbers already established in
earlier phases of this build:

1. **Data Centre**: 87.5% coverage, correctly showing Fixed Asset Register
   and Inventory Register as `NOT_UPLOADED` (no ingestion type exists for
   either yet — an honest gap, not a bug).
2. **Pre-Audit Dashboard**: Books health 55.0/100 (2 suspense accounts + 22
   of 22 unmapped accounts, matching the exact penalty formula), module
   status GST/AMBER, TDS/RED, Payroll/RED — matching the exact exception
   counts (5/1/2) and material-risk counts (0/1/2) verified in Phases 6 and
   11. `overall_status: NOT_READY` with two specific, correct blockers.
3. **Challan mapping**: TDS/PF challans correctly show `UNMAPPED` — the test
   bank statement genuinely has no matching transactions (built for GST
   testing only), an honest data-gap result, not a bug.
4. **Bank reconciliation**: after fixing a real duplicate-data incident (see
   below), correctly shows 4 real bank transactions vs 1 real GL bank
   entry, all unmatched because the two synthetic test datasets were never
   designed to reconcile against each other.
5. **AP/AR ageing**: the three genuinely-paid invoices (Om Sai Traders,
   Bharat Steel Corp, Nova Retail) correctly dropped out via real bank
   payment matching; the genuinely-unpaid ones correctly remain, aged
   correctly (Metro Logistics: 343 days, bucket 181-365).
6. **Month-End Close**: 19 tasks seeded (6 system-computed, 13 manual);
   system-computed statuses live-derived and matching the dedicated
   endpoints exactly after a consistency fix (see below).
7. **Exception sync**: 9 new exceptions created from AP ageing (1), AR
   ageing (3), and challan mapping (5) — verified the sync is idempotent
   (a second call creates zero duplicates, checked via the `_exists` guard),
   filtering by module/status/owner works, and the assign→status-transition
   workflow correctly rejects an invalid status (400) while accepting a
   valid one (204).
8. **Root cause analysis**: verified against real exceptions — a TDS
   challan payment correctly classified `MISSING_TRANSACTION`, an aged AP
   balance correctly classified `TIMING_DIFFERENCE` with impact language
   now consistent with its own MEDIUM risk level (see bug #6 below).
9. **Management query drafting**: drafted a real query from the TDS
   exception, confirmed the generated text is unambiguous (see bug #5),
   confirmed `required_information` correctly derives from the root cause,
   confirmed the linked exception moved to `ASSIGNED`, and confirmed a
   client response correctly updates only the specific query it was sent
   to — verified by checking the exact exception/query IDs rather than
   trusting list order (see the ordering note in Known Gaps).
10. **Control Tower**: every row's status, exception count, and material
    count matched exactly the numbers already independently verified
    elsewhere in this build (GST 5/0→AMBER, TDS 1/1→RED, Payroll 2/2→RED,
    AP 1/0→AMBER, AR 3/0→AMBER) — and the honest gaps rendered correctly
    too: GST's `payment` column is `false` because no GST challan
    ingestion type exists yet, and Revenue's `document` column is `false`
    because no test invoice carries e-invoice/IRN data. `overall_status`
    correctly picked up `RED` from the worst-performing rows. Caught one
    bug before this ever ran live: a copy-paste error had the Bank row
    passing the same exception count as both its total *and* material
    count, which would have wrongly treated any bank exception as material
    regardless of actual risk — fixed by computing a real,
    separately-filtered material count.

## Bugs found by actually running this (not caught by reading the code)

1. **Challan-to-bank matching could attribute one real bank transaction to
   two different "mismatch" candidates simultaneously** — caught by testing
   a 3-challan scenario instead of 2. Fixed by marking a bank transaction as
   used once it's suggested as ANY candidate, not just a confirmed match.
2. **A real data-corruption incident, caused by my own testing.** Re-uploading
   17 sample files to populate coverage data (before duplicate detection
   existed) silently doubled every row across bank transactions, journals,
   invoices, and GST/TDS/payroll data — corrupting bank reconciliation and
   challan-mapping results until traced back. This directly motivated
   building real Section 41 duplicate detection (content-hash based, with
   ASK/REPLACE/APPEND/CANCEL semantics) rather than leaving it for later.
   Cleanup itself hit a second real bug: a multi-statement `psql -c` script
   is sent as one implicit transaction, so the first cleanup attempt's
   failure on a foreign-key ordering issue silently rolled back *every*
   delete that had appeared to succeed. Fixed by re-running the cleanup in
   dependency-correct order, split into separately-committed chunks, and
   verified with a zero-row count check before reloading anything.
3. **`exception_status` enum value mismatch**: the Pre-Audit Dashboard
   queried for `status = 'RESOLVED'`, which was never a valid enum value —
   the actual schema uses `'CLOSED'`. Fixed to use the real enum.
4. **Decimal/float type mismatch**: `_load_invoices` didn't cast Postgres
   `numeric` columns to Python `float` the way `_load_bank_payments` did,
   so `compute_ageing`'s arithmetic crashed mixing `Decimal` and `float`.
5. **Self-inconsistency between Month-End Close and the dedicated ageing
   endpoints**: an early draft of the close-checklist and exception-sync
   queries skipped bank-payment matching entirely for AP/AR status
   ("omitted for brevity"), so Month-End Close reported 3 AP balances
   outstanding while `/ap/ageing` correctly reported 1. Fixed by having
   both routers import and reuse the exact same bank-matching helper
   function rather than maintaining two independent, silently-diverging
   implementations of the same logic.
6. **A second self-inconsistency, this time between an exception's risk
   level and its own root-cause explanation.** AP/AR exceptions in this
   system only ever get created once a balance is aged past 180 days (the
   sync logic never creates one for anything younger) — so every such
   exception already carries MEDIUM or HIGH risk by construction. The root
   cause classifier's first draft used a 365-day threshold and described
   anything younger as "routine ageing, Low impact," which flatly
   contradicted the MEDIUM/HIGH risk already on the same record. Fixed by
   aligning the classifier's language with the risk-assignment logic it
   describes, rather than introducing an independent, disagreeing
   threshold.
7. **Grammar/readability bugs in generated client-facing text** — "A AP
   balance" (should be "An AP balance"), and an amount reference awkwardly
   appended right after a reason string that itself ended in a number
   ("...exposure 52.50 of ₹41,500.00"), producing confusing adjacent
   figures. Both fixed, since this text is templated directly into what
   could become an actual client query document — the same "professional
   text quality matters" principle Phase 12's truncation bug established.
8. **`QueryOut(**dict(row), due_date=...)` raised `TypeError: got multiple
   values for keyword argument 'due_date'`** — `dict(row)` already contains
   a `due_date` key from the raw database row, so re-specifying it as a
   keyword argument collided. Fixed by constructing the response model
   with explicit fields instead of the fragile dict-spread pattern, in
   both the draft-query and list-queries endpoints.
9. **Exception list had no secondary sort key** — sorted only by risk
   level, so among ties (e.g. three HIGH-risk TDS exceptions), list order
   across separate calls wasn't stable. Caught when "the first item in the
   list" turned out to be a different exception than the one just updated
   in a prior call; fixed by adding a secondary `order by created_at` and
   reverified with exact-ID lookups.

## Known gaps — stated completely

- **AP/AR payment matching infers vendor/customer identity from free-text
  bank description via substring search** — a payment described differently
  than the vendor/customer master name won't match, understating "paid"
  detection. A real implementation needs a reference-number-based match.
- **Fixed Asset Register and Inventory** have no ingestion type at all —
  every related Data Centre/checklist item correctly shows `NOT_UPLOADED`
  permanently until that's built.
- **Month-End Close's 13 non-system-computed tasks** (Fixed Assets,
  Inventory, Accruals, Prepayments, Cut-off, Loans, Intercompany, Related
  Parties, FX, Provisions, Deferred Tax, Leases) are pure manual-status
  fields — no engine computes them, matching every other phase's honesty
  principle about not fabricating automation that doesn't exist.
- **No AI Root Cause Analysis (Section 61)** — exceptions have a `reason`
  string generated at creation time, but no separate classification into
  TIMING/ACCOUNTING ERROR/DUPLICATE/etc. categories.
- **No Management Query Engine (Section 62)** — `audit_query` exists in the
  schema from Phase 9 but isn't wired to auto-draft from these new
  exception sources.
- **No frontend** — every module in this entire project, across all phases,
  remains API-only. None of the new prompt's UI/UX vision (Sections
  100-111: split-screen reconciliation workspace, exception drawers, the
  Control Tower matrix) has been built.
- **PO/GRN, FAR, Inventory, Payroll-beyond-statutory, Loans, Investments,
  Intercompany, Related Parties, Leases, ESOP, Business Combinations,
  Consolidation** — none have ingestion or reconciliation logic; this
  extends the same list of gaps already documented in Phase 12's README.
