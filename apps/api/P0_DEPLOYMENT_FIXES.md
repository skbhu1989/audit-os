# AI Audit OS — P0 Deployment Fixes

Fixes the four blockers identified in the pre-deploy review, in the same
"prove it, don't assume it" spirit as everything else in this project.

## 1. CORS — was completely missing

Added `CORSMiddleware`, origins configurable via `ALLOWED_ORIGINS` (comma-
separated), defaulting to the Vite dev server origin. Verified with a real
HTTP request, not just config review: both a preflight `OPTIONS` and a real
`GET` from `http://localhost:5173` correctly receive
`Access-Control-Allow-Origin` in the response.

## 2. Secrets fail loudly in production instead of silently defaulting

`app/security.py` and `app/db.py` now check `ENVIRONMENT`: if it's
`production` and `JWT_SECRET`/`DATABASE_DSN` aren't set, the app refuses to
start rather than silently running with the dev fallback values. Verified
both directions: confirmed it genuinely raises with no secret set and
`ENVIRONMENT=production`, and confirmed it genuinely starts once one is
provided. Development behavior (`ENVIRONMENT` unset) is unchanged — checked
by running the existing 18-test suite before adding anything new.

## 3. Rate limiting on /auth/signup and /auth/login

A minimal in-memory sliding-window limiter (signup: 5/hour, login: 10/5min),
reading `X-Forwarded-For` for the real client IP behind a reverse proxy.
Explicitly documented as a single-instance limitation — it doesn't
coordinate across multiple server instances behind a load balancer, since
no Redis/shared-cache layer exists anywhere in this build. A real
horizontally-scaled deployment needs that; this is the correctly-scoped
version of what's actually buildable without infrastructure this system
doesn't have.

Verified by actually hammering the endpoint: 12 rapid login attempts
correctly allowed the first 10 and blocked attempts 11-12 with 429 and a
Retry-After header.

A real conflict this surfaced: FastAPI's TestClient reports one fixed fake
client address for every request, so the existing test suite's per-test
firm creation (each test signs up a fresh firm) collided into a single
rate-limit bucket after ~5 tests. Fixed correctly — not by weakening the
limiter for real traffic, but by having the limiter recognize
ENVIRONMENT=test (which conftest.py now sets explicitly) and skip itself
only in that deliberate context. The limiter's own core logic still has two
dedicated regression tests (test_rate_limiting.py) that bypass that flag
specifically to verify blocking, isolation-between-clients, and
X-Forwarded-For handling all still work.

## 4. Missing deployment artifacts

- requirements.txt didn't exist at all. Built from an actual scan of every
  import across the codebase (not a guess), with real pinned versions read
  from what's actually installed. Proved it's genuinely complete by
  installing into a brand-new, empty virtualenv and importing the full app
  — which failed on the first attempt (missing email-validator, needed by
  pydantic.EmailStr in the auth models), fixed, and reverified clean.
- Dockerfile — standard slim-Python pattern, runs as non-root, sets
  ENVIRONMENT=production by default (so the fail-loudly secret checks are
  live in any real container). Honestly caveated: no Docker is available in
  this sandbox, so the image was never actually built or run — only the
  pip install layer is proven correct (it's the identical command just
  verified in the clean-venv test above). The rest follows standard,
  well-established patterns but is unverified in this environment.
- .env.example — documents all four environment variables this system
  actually reads, with a note on each about why it matters (e.g., using the
  table-owner DB role instead of app_runtime here would silently defeat
  every RLS tenant-isolation guarantee in the system).

## Final verification

All 20 tests pass after every change above, run together, against the real
test database — including 2 new tests added this session for the rate
limiter itself.

## What's still NOT fixed — P1/P2, correctly not attempted in this pass

Everything else from the original pre-deploy review stands as previously
documented: no refresh tokens, synchronous file processing, no CI pipeline,
and — the one that matters most for actually trusting this before a real
launch — the frontend has still never been opened in an actual browser.
This session fixed exactly the four P0 items that were scoped, nothing more
and nothing pretended.
