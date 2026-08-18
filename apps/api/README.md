# AI Audit OS — Phase 3: Auth & Client/Engagement Management API

A FastAPI service implementing signup, login, MFA, and RBAC-gated client/engagement
management on top of the Phase 2 schema. **Every endpoint below was run against a
live PostgreSQL instance and a live running server** — not just written and assumed
correct. Four real bugs were found and fixed this way; see "Bugs found by testing"
below.

## Running it

```bash
pip install -r requirements.txt
# apply migrations 001-012 from ../db/migrations first, then:
export JWT_SECRET="<random-secret>"
export DATABASE_DSN="postgresql://app_runtime:<password>@<host>:5432/audit_os"
uvicorn app.main:app --reload
```

## What's implemented

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/signup`, `POST /auth/login`, `POST /auth/mfa/enroll`, `POST /auth/mfa/verify` |
| Clients | `GET /clients`, `POST /clients`, `GET /clients/{id}` |
| Engagements | `GET/POST /engagements`, `PATCH /engagements/{id}/materiality`, `POST /engagements/{id}/team`, `GET/POST /engagements/{id}/periods` |
| Health | `GET /health` |

RBAC: read endpoints are open to any authenticated role; writes (create client,
create engagement, set materiality, assign team) are restricted to
FIRM_ADMIN/PARTNER/MANAGER via `require_roles(...)`, enforced server-side
regardless of what a UI shows — verified by testing an ARTICLE-role token against
each gated endpoint and confirming 403.

## What was actually verified end-to-end (not just written)

1. **Signup** creates a firm + FIRM_ADMIN user + credential row; duplicate email
   correctly 409s (via the real unique constraint, not a racy pre-check).
2. **Login** succeeds with correct credentials, 401s on wrong password, 403s on a
   deactivated account path.
3. **Tenant isolation via RLS, exercised through the API, not just raw SQL**:
   seeded two separate firms, each created its own client, and confirmed each
   firm's `GET /clients` returns *only* its own data. Firm A requesting Firm B's
   client by ID gets a clean **404**, not a 403 — so the response never confirms
   another tenant's record even exists.
4. **RBAC**: an ARTICLE-role token gets 403 on `POST /clients` and
   `PATCH /engagements/{id}/materiality`, but 200 on read endpoints — confirming
   the permission matrix from the Phase 1 spec is enforced, not just documented.
5. **Engagement lifecycle**: create engagement, duplicate (same client+FY) 409s,
   materiality PATCH persists and is visible on the next read, team assignment
   succeeds, period creation succeeds.
6. **Audit trail**: queried `audit_trail_event` directly after the materiality
   PATCH and confirmed it captured the actual new value (₹46.8L), not just that
   *some* change happened.
7. **MFA**: enrolled a TOTP secret, wrong code correctly rejected with 400 and
   MFA stays disabled, correct code enables it. Login without a code then
   returns `mfa_required: true` and an empty token (can't be used); login with
   the correct current TOTP code returns a real token; wrong code 401s.

## Bugs found by actually running this (not caught by reading the code)

1. **`SET LOCAL x = $1` isn't valid Postgres** — `SET` is a utility statement and
   doesn't accept bind parameters. Fixed by switching every tenant-context call
   to `SELECT set_config('app.current_firm_id', $1, true)`, which is the
   parameterized equivalent.
2. **`INSERT ... RETURNING` is filtered by the SELECT RLS policy, not the INSERT
   policy.** Creating a brand-new `firm` row via `RETURNING id` always came back
   empty, because `app.current_firm_id` can't be set to an id we don't have yet.
   Fixed by generating the UUID client-side, setting tenant context to that id
   *before* the insert, and skipping `RETURNING` entirely for that one row.
3. **The generic audit-trail trigger assumed every table has an `engagement_id`
   column.** `client` and `engagement` themselves don't fit that shape (client
   IS the firm-scoped root; engagement's own `id` is what other tables call
   `engagement_id`). Discovered when a routine cleanup `DELETE FROM client`
   crashed with a PL/pgSQL error. Fixed with two dedicated trigger functions
   (`fn_log_audit_trail_client`, `fn_log_audit_trail_engagement`) instead of
   forcing one generic function to handle incompatible row shapes.
4. **`passlib`'s bcrypt backend is broken against current `bcrypt` package
   versions** (`passlib` reads `bcrypt.__about__.__version__`, which newer
   `bcrypt` releases removed) — silently corrupted every password hash/verify
   call. Switched to calling the `bcrypt` library directly.

All four fixes are reflected in the code and in `db/migrations/011...sql`
(re-run migration 011 if you applied an earlier copy).

## Known gaps / not yet built

- **No refresh tokens** — JWTs are 8-hour, non-revocable until expiry. A
  production system needs a revocation list or short-lived-access +
  refresh-token pattern, especially since MFA can be enabled/disabled mid-session.
- **No rate limiting** on `/auth/login` or `/auth/signup` — needed before this
  is internet-facing (brute force / signup spam).
- **`firm` INSERT is deliberately RLS-permissive** (see migration 011's comment)
  so bootstrap signup works. In production this needs an application-level
  gate — email verification, invite codes, or admin approval — since the
  database alone won't stop someone from creating unlimited firms.
- **No client-portal role/endpoints yet** — `CLIENT_USER` exists in the role
  enum but has no working paths; that's PBC/client-portal territory from a
  later phase.
- **Engagement partner/manager assignment on creation is minimal** (only
  auto-assigns if the creator is a PARTNER) — proper assignment should go
  through the `/team` endpoint explicitly rather than being inferred.
- Client/engagement update (PATCH beyond materiality) and delete endpoints
  aren't built yet — only create/read plus the one materiality-specific patch.

## Next phase

Phase 4 per the roadmap is data ingestion — Excel/CSV/Tally parsers writing into
the Universal Data Model (trial_balance_line, journal, journal_line, vendor,
customer) built in Phase 2. That's the natural next target, or Phase 5 (TB
mapping + GL engine logic) if you'd rather build analysis before ingestion
plumbing.
