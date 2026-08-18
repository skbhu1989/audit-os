# AI Audit OS — Phase 9: Working Papers + Evidence Management

Auto-drafts working papers (Section 41 structure) from the real reconciliation
and JE-risk data already sitting in the database from Phases 5-6, and
implements a genuine prepare → review → approve sign-off state machine with
segregation-of-duties enforcement — verified with three separate real user
identities, not a single test user wearing three hats.

## What's implemented

| Endpoint | Purpose |
|---|---|
| `POST .../working-papers/auto-draft/gst` | drafts one WP per GST reconciliation type from real run data |
| `POST .../working-papers/auto-draft/tds` | drafts the TDS reconciliation WP |
| `POST .../working-papers/auto-draft/journal-testing` | drafts the JE testing WP from risk-scoring results |
| `GET .../working-papers`, `GET .../working-papers/{id}` | list / detail |
| `POST .../working-papers/{id}/prepare` | DRAFT → PREPARED |
| `POST .../working-papers/{id}/review` | PREPARED → REVIEWED (blocks the preparer) |
| `POST .../working-papers/{id}/approve` | REVIEWED → APPROVED (blocks the preparer; can refine the conclusion) |
| `POST .../working-papers/{id}/evidence` | link an already-uploaded document as evidence |
| `GET .../working-papers/{id}/evidence` | list linked evidence |

## Design: drafts are templated, not LLM-generated

Per the architecture doc's separation of concerns (Section B), `working_papers.py`
builds objective/population/sample/conclusion text from deterministic
templates driven by the actual reconciliation numbers — not from an LLM
guessing at what a working paper should say. Every auto-drafted conclusion is
explicitly marked "DRAFT — pending reviewer sign-off, NOT a final conclusion"
(Section 50/CL: AI drafts, humans conclude), and the approve endpoint lets a
partner override the conclusion text entirely before signing off — confirmed
working live (see verification #4 below).

## Segregation of duties (SA 220), enforced and verified with real distinct users

The same person cannot prepare and then review or approve their own working
paper. This isn't just a code comment — it was tested with three separate
minted user identities (a FIRM_ADMIN preparer, a distinct MANAGER reviewer, a
distinct second PARTNER approver) and confirmed that the *same* preparer
attempting to review or approve their own work gets a 403, while a genuinely
different qualifying user succeeds.

## What was actually verified end-to-end

1. Auto-drafted all 5 working papers (3 GST recon types, TDS, journal
   testing) from real Phase 5/6 data — every number in the generated
   conclusion text (4 records/2 matched/1 partial/1 unmatched, ₹52.50
   interest exposure, 0 HIGH/CRITICAL journals) matches the underlying data
   exactly, confirmed by cross-referencing against the Phase 6 test output.
2. Full state machine: prepare (204) → re-prepare rejected (409, wrong
   status) → same-user review rejected (403, segregation of duties) →
   different-user (MANAGER) review succeeds (204) → preparer-attempts-approve
   rejected (403) → different PARTNER approves (204) with a refined final
   conclusion that correctly overwrote the auto-drafted text.
3. Final state confirmed via GET: `status=APPROVED`, `preparer_id`,
   `reviewer_id`, `approver_id` all populated with three genuinely different
   user ids — not the same id three times.
4. Evidence linking: attached the real `gstr1.csv` document (already in the
   system from Phase 6's upload) to its corresponding working paper, listed
   it back, and confirmed via direct DB query that a minimal `audit_procedure`
   row was auto-created with the correct `assertions` array inherited from
   the working paper — not a placeholder value.

## Bugs found by actually running this (not caught by reading the code)

1. **`fs_assertion` enum value mismatch.** Migration 007's `fs_assertion`
   Postgres enum uses uppercase values (`COMPLETENESS`, `ACCURACY`, ...) with
   **no `OCCURRENCE` value at all** — Section 41's assertion list never
   included it. My first draft used human-readable mixed-case strings
   including `"Occurrence"`, which isn't a valid enum value under any
   casing. Every auto-draft call 500'd until fixed: the two straightforward
   mismatches were case fixes, but occurrence has no real equivalent in this
   schema — mapped to `EXISTENCE` with an explicit comment explaining it's
   the nearest available concept, not a hidden approximation.
2. **`audit_procedure.assertions` is `NOT NULL`**, but the auto-create-a-
   minimal-procedure-on-first-evidence-link code only supplied `engagement_id`
   and `title`. Fixed by seeding `assertions` from the working paper's own
   `fs_assertion` array — logically correct anyway, since the procedure and
   its parent working paper are testing the same assertions by construction,
   not an arbitrary placeholder.

## Known gaps / not yet built

- **No PBC/query auto-generation wired to working papers yet** — a working
  paper's "auditor should obtain client explanation" conclusion text doesn't
  yet automatically create an `audit_query` row; that linkage exists in the
  schema (`audit_query.exception_id`) but isn't triggered from this phase.
- **Working paper versioning creates a new row on re-draft** (confirmed
  working via the `version`/`supersedes_wp_id` columns) but there's no
  endpoint yet to view the version history or diff between versions.
- **CARO/IFC working papers aren't built** — this phase covers GST, TDS, and
  JE testing only, matching what Phases 5-6 actually produce data for.
- **The `EXISTENCE`-for-`OCCURRENCE` substitution** (bug #1 above) is a real,
  if minor, terminology gap — a future migration should probably add
  `OCCURRENCE` to the `fs_assertion` enum rather than permanently
  approximating it.

## Next phase

Per the roadmap, the AI assistant layer — narrating these deterministic
results (reconciliation exceptions, risk scores, working paper conclusions)
in the ANSWER/DATA USED/CALCULATION/STANDARD/EVIDENCE/IMPLICATION/PROCEDURE
format from the original spec, backed by real data instead of the earlier
synthetic-data prototype.
