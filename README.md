# AI Audit OS

An AI-powered Indian Financial Pre-Audit & Statutory Audit platform —
accounting, GST/TDS reconciliation, CARO/IFC, working papers, and a
finance-intelligence layer, built as a genuine multi-phase engineering
project with every module tested against real data.

**Live demo**: see [`RENDER_DEPLOY.md`](RENDER_DEPLOY.md) to stand up your
own — frontend on GitHub Pages, backend + Postgres on Render.

## What's here

```
apps/api/          FastAPI backend — ~40 routers, 29 migrations, real
                    GST/TDS/Payroll/Bank/FAR/Inventory/Loans/Investments/
                    Intercompany reconciliation engines, CARO/IFC, working
                    papers with sign-off, an integration abstraction layer,
                    and a finance-intelligence module
apps/api/tests/     20-test pytest regression suite (auth, tenant
                    isolation, RLS, numeric correctness of the actual
                    financial arithmetic, segregation-of-duties sign-off)
frontend/           React + Vite + Tailwind — ~22 pages, wired to the real
                    API, styled as a statutory-ledger-themed interface
db/migrations/      29 SQL migrations, applied in order by db/migrate.sh
e2e-browser-tests/  A real, rerunnable headless-Chromium test suite that
                    drives the actual built frontend through real user flows
docker-compose.yml  One-command local stack: Postgres + migrate + API + UI
```

## Quickstart (local, Docker)

```bash
cp .env.example .env   # fill in real secrets
docker compose up --build
```

Frontend at `http://localhost:8080`. See [`DEPLOYMENT.md`](DEPLOYMENT.md)
for what's actually been verified about this path and what hasn't.

## Quickstart (local, no Docker)

```bash
# Database
createdb audit_os
APP_RUNTIME_PASSWORD=<pick one> bash db/migrate.sh audit_os

# Backend
cd apps/api && pip install -r requirements.txt -r requirements-dev.txt
DATABASE_DSN=postgresql://app_runtime:<password>@localhost/audit_os JWT_SECRET=<pick one> \
  uvicorn app.main:app --reload

# Tests
pytest tests/ -v

# Frontend
cd ../../frontend && npm install && npm run dev
```

## Documentation index

Start here:
- [`DEPLOYMENT.md`](DEPLOYMENT.md) — Docker-based deployment, honestly
  scoped to what was actually tested
- [`RENDER_DEPLOY.md`](RENDER_DEPLOY.md) — GitHub Pages + Render, step by step
- [`apps/api/TESTING.md`](apps/api/TESTING.md) — what the regression suite
  covers and doesn't
- [`e2e-browser-tests/BROWSER_TESTING.md`](e2e-browser-tests/BROWSER_TESTING.md)
  — the real headless-browser verification and what it found
- [`apps/api/CTO_TECHNICAL_AUDIT.md`](apps/api/CTO_TECHNICAL_AUDIT.md) —
  a systematic security/architecture audit with real findings and fixes
- [`apps/api/P0_DEPLOYMENT_FIXES.md`](apps/api/P0_DEPLOYMENT_FIXES.md) —
  CORS, secrets, rate limiting, requirements.txt

Module-by-module build notes (each documents what's real, what's tested,
what's an honest known gap — not just a feature list):
[`apps/api/PHASE4_INGESTION.md`](apps/api/PHASE4_INGESTION.md) ·
[`PHASE5_ANALYTICS.md`](apps/api/PHASE5_ANALYTICS.md) ·
[`PHASE6_RECONCILIATION.md`](apps/api/PHASE6_RECONCILIATION.md) ·
[`PHASE7_RISK_ENGINE.md`](apps/api/PHASE7_RISK_ENGINE.md) ·
[`PHASE9_WORKING_PAPERS.md`](apps/api/PHASE9_WORKING_PAPERS.md) ·
[`PHASE10_AI_ASSISTANT.md`](apps/api/PHASE10_AI_ASSISTANT.md) ·
[`PHASE11_PAYROLL_COMPLIANCE.md`](apps/api/PHASE11_PAYROLL_COMPLIANCE.md) ·
[`PHASE12_CARO_IFC_REPORTING.md`](apps/api/PHASE12_CARO_IFC_REPORTING.md) ·
[`PRE_AUDIT_MODULE.md`](apps/api/PRE_AUDIT_MODULE.md) ·
[`FAR_INVENTORY_MODULE.md`](apps/api/FAR_INVENTORY_MODULE.md) ·
[`LOANS_INVESTMENTS_MODULE.md`](apps/api/LOANS_INVESTMENTS_MODULE.md) ·
[`INTERCOMPANY_MODULE.md`](apps/api/INTERCOMPANY_MODULE.md) ·
[`API_INTEGRATION_LAYER.md`](apps/api/API_INTEGRATION_LAYER.md) ·
[`FINANCE_INTELLIGENCE_MODULE.md`](apps/api/FINANCE_INTELLIGENCE_MODULE.md)

## The engineering discipline this project holds itself to

Every module above was built the same way: real logic, unit-tested by
hand-computed examples, wired to a router, tested against real (synthetic
but realistic) data through the actual running API — and every "Known
Gaps" section in every doc above is a deliberate, honest boundary, not an
oversight. Where something isn't built, the docs say so plainly rather than
implying it. Where a bug was found — and dozens were, across every phase —
the fix and the real test that caught it are both documented, not just the
final clean state.

## What's genuinely NOT built

Leases (Ind AS 116), ESOP, Business Combinations, Consolidation, Deferred
Tax, a true Related Party detection engine (blocked without director/
shareholder data ingestion), Document Intelligence/OCR, a real regulatory
knowledge base (only citation labels exist), and a PBC/client portal. No
live GST/TDS/MCA/Bank/Tally/Zoho connector exists — by design, stated
explicitly in `API_INTEGRATION_LAYER.md`: this system never fakes a live
connection it doesn't have.
