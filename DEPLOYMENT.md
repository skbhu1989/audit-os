# AI Audit OS — Deployment Guide

One command stands up the whole stack:

```bash
cp .env.example .env   # fill in real secrets — compose refuses to start without them
docker compose up --build
```

This brings up, in order: Postgres -> migrations (runs once, applies all 29
files, sets the real app_runtime password, then exits) -> backend (waits
for migrations to genuinely finish, not just for Postgres to accept
connections) -> frontend (nginx, serving the built app and proxying /api/*
to the backend). Frontend is reachable at http://localhost:8080.

## What was actually tested, and how — read this before trusting any of it

No Docker or docker-compose is available in this build sandbox, so the full
containerized stack was never actually brought up end-to-end as one unit.
Rather than leave that untested, every individual piece of what compose
orchestrates was tested for real, outside Docker, using the same
underlying commands:

| Piece | How it was actually verified |
|---|---|
| Migration runner (db/migrate.sh) | Ran against a genuinely fresh, empty Postgres database (not the long-running dev one) — all 29 files applied cleanly, final schema independently checked (62 tables, exactly 5 correctly RLS-exempt). Ran a second time with APP_RUNTIME_PASSWORD set and confirmed the password genuinely changed in the database (real SCRAM hash, not the placeholder). |
| Backend -> Postgres connection | The exact DATABASE_DSN shape compose uses (app_runtime role, real password) was used to start the real FastAPI app and pass its own /health check. |
| CORS, rate limiting, secret-safety checks | All re-verified in this same session with real HTTP requests (see P0_DEPLOYMENT_FIXES.md) — unchanged by anything in this pass. |
| Frontend production build | Rebuilt with VITE_API_BASE=/api (the production shape, not the dev-only Vite proxy) — builds clean. |
| nginx config (frontend/nginx.conf) | nginx was installed in this sandbox and actually run against the real production build output and the real backend — proxying, static serving, and SPA-routing fallback all independently confirmed with real HTTP requests. |
| The exact CI sequence (fresh DB -> migrate -> install deps -> test) | Run locally end-to-end, identically to what .github/workflows/test.yml does — 20/20 tests passed against a database that had never existed before that run. |

What genuinely remains unverified: the actual `docker build` steps
(Dockerfile syntax follows standard, well-established patterns, but was
never run), and the full multi-container orchestration (service startup
ordering, health-check timing, inter-container networking) as one unit.
Every piece it's built from is proven; the assembly itself is not.

## A real bug this process found, worth knowing about

While testing migrate.sh's password-setting feature against a throwaway
test database, the app_runtime password changed for every database in the
shared Postgres cluster — including the unrelated long-running dev
database this whole project has used all session — because Postgres roles
are cluster-wide, not per-database. Harmless in the real deployment shape
(one Postgres instance per environment), but worth knowing if you ever run
this against a shared/multi-database cluster. Documented directly in
migrate.sh's own comments, not just here.

## Manual / non-Docker deployment

If you're not using Docker:

```bash
# 1. Database
createdb audit_os
APP_RUNTIME_PASSWORD=<real-password> bash db/migrate.sh audit_os

# 2. Backend
cd apps/api
pip install -r requirements.txt
ENVIRONMENT=production \
DATABASE_DSN=postgresql://app_runtime:<real-password>@localhost:5432/audit_os \
JWT_SECRET=<real-secret> \
ALLOWED_ORIGINS=https://your-frontend-domain.example.com \
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 3. Frontend
cd frontend
VITE_API_BASE=https://your-api-domain.example.com npm run build
# serve dist/ with any static file host; ensure ALLOWED_ORIGINS above
# includes wherever it ends up served from
```

## What's still genuinely not done

Everything flagged in CTO_TECHNICAL_AUDIT.md and P0_DEPLOYMENT_FIXES.md
that wasn't scoped to this pass: no refresh tokens, synchronous file
processing (fine at tested scale, will bottleneck under real load), no
load/performance testing, and — still the largest single caveat on the
whole project — the frontend has never been opened in an actual browser,
only build-compiled and network-tested at the proxy/HTTP level.
