# AI Audit OS — CTO Technical Audit

Per the AI CTO mandate (bridging software engineering rigor with the finance
domain work already built), this is a systematic audit of the existing
codebase — not a new feature, and not a generic "here's what good
engineering looks like" essay. Every finding below was checked against the
real, running system; nothing here is speculative.

## Finding 1 (Critical, Fixed): Two more instances of a recurring bug class

This exact bug — a generic audit-trail trigger assuming every table has an
`engagement_id` column — has now been found and fixed six times across this
build (`client`, `engagement` in Phase 3; `journal_line` in Phase 4;
`reconciliation_match` in Phase 6; and two more found this round:
`client_gstin` and `rule_version`).

Why the first four fixes didn't prevent these two: each prior fix was found
by feature testing — building and testing the specific endpoint that
happened to write to that table. `client_gstin` never had a write endpoint
built (multi-GSTIN management was schema-only), and `rule_version` was only
ever written once, via a migration's own seed INSERT — which ran before the
trigger existed. Neither bug could have been found by more feature testing;
they required a systematic audit of every trigger-to-table pairing, checking
each one's actual schema regardless of whether a feature currently exercises
it.

- `client_gstin`: fixed with a dedicated trigger resolving firm via
  `client_id -> client.firm_id` (same pattern as five prior fixes).
- `rule_version`: not patched with a fake tenant ID — it's genuinely
  platform-level reference data with no firm/engagement relationship in its
  lineage at all. `audit_trail_event.firm_id` is NOT NULL, so this table
  structurally cannot fit the tenant-scoped audit trail. The trigger was
  removed entirely, with the gap documented (platform-level reference data
  has no changelog mechanism in this system) rather than hacked around.

Both fixes were verified by actually exercising the previously-untested
write paths (insert/update/delete on `client_gstin`, insert on
`rule_version`) — not just "it should work now."

Migration: `028_audit_trigger_systematic_fix.sql`

## Finding 2 (Serious, Fixed): 13 tables with real client data had no RLS at all

A systematic check of every table's row-security flag found 18 tables with
row-level security disabled. Five are legitimately global reference data
(`caro_clause`, `ifc_control`, `rule`, `rule_version`,
`integration_provider`) — correctly exempt, no tenant relationship exists.

The other 13 held real client/audit data with zero database-level tenant
isolation, protected only by whatever `WHERE engagement_id = $1` clause
application code happened to include — exactly the "defense only in the
application layer" pattern this system's own founding security principle
(stated in Phase 2) exists to protect against: "even if application code has
a bug, RLS protects the data." For 13 tables, that guarantee was false this
whole time.

Most seriously: `audit_trail_event` — the audit log itself — had no tenant
isolation. A bug in any application query touching this table could have
leaked one firm's activity log to another.

The other 12: `journal_line`, `payment`, `receipt`, `credit_debit_note`,
`purchase_order`, `grn`, `return_filing`, `audit_evidence`,
`working_paper_evidence`, `working_paper_exception`, `extracted_field`,
`reconciliation_match`, `reconciliation_exception`.

Fix verified, not just applied: after adding policies to all 13 tables,
directly tested tenant isolation on the two most consequential
(`journal_line`, `audit_trail_event`) using the same two-firm methodology
established since Phase 3 — confirmed real data (12 journal lines, 287 audit
events) visible with the correct tenant context set, and zero visible with
no context set. Fails closed, as designed.

Migration: `029_rls_coverage_fix.sql`

## Finding 3 (Informational, no action needed): Secrets hygiene

`JWT_SECRET` and the database password both use the
`os.environ.get(KEY, "dev-fallback-value")` pattern — the fallback is never
used once the real environment variable is set in deployment, so this isn't
a live vulnerability. Flagged for completeness: any real deployment must set
`JWT_SECRET` and `DATABASE_DSN` via environment variables — the fallback
values exist for local development convenience only and are intentionally
named to signal that.

## What this audit did NOT cover (honest scope)

This was a targeted audit (recurring bug-class + RLS coverage + secrets),
not an exhaustive CTO review. Explicitly not covered this round, and worth a
dedicated pass:

- No automated regression test suite exists. Every verification across this
  entire build — every phase, every bug found and fixed — was a manual,
  live curl-based test session. Nothing prevents a future change from
  silently breaking, say, Phase 3's tenant isolation or Phase 6's GST
  reconciliation math. This is the single largest engineering risk in the
  codebase and the natural next audit priority: a real pytest suite covering
  auth/tenant-isolation, the core reconciliation engines, and the sign-off
  state machines, so regressions are caught automatically instead of
  requiring another multi-hour manual session to rediscover.
- Dependency audit — `requirements.txt` reflects what was actually installed
  and used, but no vulnerability scan (e.g. pip-audit) has been run against it.
- No load/performance testing — every test in this build used a small
  synthetic dataset (one company, a handful of transactions per module);
  behavior at real transaction volumes (thousands of journal entries, large
  trial balances) is unverified.
- API rate limiting, CORS configuration, request size limits — not reviewed
  or hardened in this pass.
- The consolidated Technical Debt Register implied by every phase's "Known
  Gaps" section (no async job queue, no caching, synchronous ingestion, no
  refresh tokens, etc.) exists scattered across ~20 phase READMEs but has
  never been consolidated into one prioritized (P0/P1/P2) document — a
  natural next deliverable if a full CTO-style backlog review is wanted.
