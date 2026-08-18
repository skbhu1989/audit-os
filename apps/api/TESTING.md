# AI Audit OS — Regression Test Suite

The single largest engineering gap flagged in the CTO Technical Audit: every
verification across this entire multi-phase build was a manual, ephemeral
`curl`-based test session. This is the fix — a real, automated `pytest`
suite that actually runs, actually passes, and actually catches the exact
bug classes this project found the hard way.

## Running it

```bash
pip install -r requirements.txt -r requirements-dev.txt

# One-time setup: a dedicated test database, kept separate from any real
# working database so the suite can never touch production/dev data.
createdb audit_os_test
for f in ../db/migrations/*.sql; do
  psql -d audit_os_test -v ON_ERROR_STOP=1 -f "$f"
done

pytest tests/ -v
```

18 tests, ~5 seconds, all passing against a real Postgres instance with all
29 migrations applied — confirmed by actually running it, not assumed.

## What's covered, and why each test exists

| File | Protects against |
|---|---|
| `test_auth_and_isolation.py` | Signup/login, tenant isolation at the API layer, RBAC — regression tests for the exact `SET LOCAL` parameter bug, the `INSERT...RETURNING`/RLS interaction bug, and the broken `passlib` bcrypt backend, all found in Phase 3 |
| `test_database_security.py` | RLS enforcement **at the database layer directly** (via raw `asyncpg`, bypassing the API entirely) — this is deliberately a second, independent layer under the API tests, since a missing RLS policy wouldn't necessarily show up if every current API endpoint happens to include the right `WHERE` clause. Includes direct regression tests for the two most serious CTO audit findings: `journal_line` and `audit_trail_event` had zero tenant isolation until migration 029 |
| `test_ingestion_and_reconciliation.py` | The Phase 4 non-tying-TB-still-persists bug, the Pre-Audit Module duplicate-upload data-corruption incident, and the Phase 11 payroll false-positive (a completely normal, on-time PF payment being flagged as two separate exceptions) |
| `test_reconciliation_accuracy.py` | **Numeric correctness of the actual financial arithmetic** — not just that endpoints respond correctly, but that a deliberately-engineered ₹20,000 GST mismatch and a deliberately-engineered ₹225.00 TDS interest calculation come back as exactly those figures, not approximately or roughly |
| `test_working_paper_signoff.py` | Segregation of duties (SA 220) with three **genuinely distinct** users — the same pattern of proof used throughout manual testing (a preparer cannot review or approve their own work), now automated |

## Design choices worth knowing about

- **Every test creates its own firm/client/engagement** via real signup and
  API calls (unique email per test run) rather than relying on shared fixture
  state or transaction rollback — slower, but it means each test exercises
  the exact same code path a real user goes through, and tests can run in
  any order or in parallel without interfering with each other.
- **A separate `audit_os_test` database**, never the real one — the suite
  cannot accidentally corrupt real client data the way the Pre-Audit Module
  incident did to the manually-tested `audit_os` database earlier in this
  build.
- **No mocking of the database or business logic** — every test runs against
  a real Postgres instance with real RLS policies, real triggers, and the
  real parsing/reconciliation engines. This is intentionally closer to an
  integration test suite than a unit test suite, matching how every bug in
  this project was actually found (by running the real system, not by
  testing an isolated function in isolation).

## Honest coverage gaps — what this suite does NOT protect against yet

- **Only 2 of ~12 reconciliation domains have numeric-accuracy tests** (GST,
  TDS). Payroll, Bank, Challan Mapping, FAR, Inventory, Loans, Investments,
  Intercompany, and the Risk Engine all have real, hand-computed expected
  results verified manually during their respective phases, but none of
  those specific numbers are locked into an automated regression test yet.
- **CARO's sign-off state machine** is untested (only Working Papers' is) —
  same underlying pattern, not yet duplicated into a test.
- **No test for the AI Assistant's deterministic answers** or the Finance
  Intelligence module (master data intelligence, capitalization review,
  accrual gap calculator) — all genuinely tested manually in their own
  phases, none locked into this suite yet.
- **No performance/load testing** — every test uses a single small dataset;
  behavior at real transaction volumes is unverified by this suite or any
  other part of this project.
- **No CI configuration** — this suite is runnable, but nothing currently
  triggers it automatically on a code change (no GitHub Actions/CI pipeline
  config exists in this repository).

The honest summary: this suite meaningfully de-risks the specific bug
classes this project actually encountered and fixed, but it is a starting
foundation, not comprehensive coverage of the ~40 routers and ~25 domain
modules built across this entire project.
