# Going Live: GitHub Pages (frontend) + Render (backend)

## 1. Push this repo to GitHub

```bash
cd audit-os   # this repo
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

## 2. Turn on GitHub Pages

Repo Settings -> Pages -> Source -> GitHub Actions. That's it — the
included .github/workflows/deploy-frontend.yml handles the rest on every
push to main. Your frontend will be live at:

```
https://YOUR_USERNAME.github.io/YOUR_REPO/
```

It'll build successfully on the first push, but won't be able to reach a
backend yet — that's step 3.

## 3. Deploy the backend on Render

1. render.com -> New -> Blueprint -> connect this repo. Render reads
   render.yaml and provisions a Postgres database and the API web service
   automatically.
2. The one manual step that matters — do this before the app is usable:
   - Render's dashboard -> your new Postgres database -> copy the External
     Connection String (this is the database owner role).
   - From your own machine (or Render's Shell tab on the web service):
     ```bash
     APP_RUNTIME_PASSWORD=<generate one: python3 -c "import secrets; print(secrets.token_hex(24))"> \
       bash db/migrate.sh "<the owner connection string you copied>"
     ```
     This applies all 29 migrations and creates app_runtime — a separate,
     non-owner role. This step is deliberately not automated — Postgres
     bypasses row-level security entirely for the database owner, so
     wiring the app to connect as the owner (which Render's blueprint
     would do automatically if DATABASE_DSN were auto-filled) would
     silently disable every tenant-isolation guarantee in this system,
     with no error to ever notice. Running it yourself, once, is the
     tradeoff for that not happening by accident.
   - Build the real DATABASE_DSN by taking the owner connection string and
     swapping the username/password for app_runtime/<the password you just
     generated> — everything else (host, port, database name) stays the
     same.
   - Render dashboard -> the audit-os-api service -> Environment -> set
     DATABASE_DSN to that string.
3. Update ALLOWED_ORIGINS on the web service to your real GitHub Pages URL
   from step 2 (it defaults to a placeholder in render.yaml).
4. Redeploy the web service (Render does this automatically when you save
   env var changes). Confirm it's healthy:
   ```bash
   curl https://your-service.onrender.com/health
   ```

## 4. Connect frontend to backend

Repo Settings -> Secrets and variables -> Actions -> Variables -> add
BACKEND_API_URL = https://your-service.onrender.com/api
(deploy-frontend.yml already reads this — it just wasn't set until now).

Push anything to main (or re-run the workflow manually from the Actions
tab) to rebuild the frontend pointing at the real backend.

## What you'll have at the end

- A real, public frontend URL on GitHub Pages, auto-deploying on every push
- A real, public backend URL on Render, running the actual FastAPI app
  against a genuinely migrated, RLS-protected Postgres database
- CI (.github/workflows/test.yml) running the real 20-test regression
  suite on every push and PR

## Honest limitations of this specific path

- Render's free tier sleeps after inactivity — the first request after an
  idle period takes ~30-60 seconds while it wakes up. Fine for a demo or
  low-traffic use; upgrade the plan for anything real.
- Render's free Postgres is deleted after 30 days unless upgraded — don't
  put real client data on the free tier long-term.
- Everything else genuinely tested throughout this build (RLS isolation,
  CORS, rate limiting, the reconciliation engines, the actual browser
  session) carries over unchanged — this runbook only concerns where the
  already-verified code runs, not re-verifying the code itself.
