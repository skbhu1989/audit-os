# AI Audit OS — Frontend

The first real frontend in this entire project — every prior UI (the early
synthetic-data prototype) was disconnected from the actual backend. This one
calls the live FastAPI API built across Phases 2–12 and the Pre-Audit
Module, using the exact same ledger/statutory-register design language
(navy/ink sidebar, paper background, serif headers, mono numeric data, gold
seal accents) established in that first prototype — carried forward
deliberately for visual continuity, but now wired to real data.

## Running it

```bash
npm install
npm run dev          # starts on http://localhost:5173, proxies /api to the backend
```

By default the dev server proxies `/api/*` to `http://127.0.0.1:8000` (set
`VITE_BACKEND_URL` to point elsewhere). Start the backend first:

```bash
# from apps/api/
uvicorn app.main:app --reload
```

For a production build:
```bash
npm run build        # outputs to dist/
```
Set `VITE_API_BASE` at build time if the frontend and backend are deployed on
different origins (defaults to `/api`, which assumes a reverse proxy).

## What's covered

Every screen calls a real endpoint — nothing here renders from mock data:

| Page | Backend module |
|---|---|
| Control Tower (`/dashboard`) | Section 51 signature dashboard + Pre-Audit summary |
| Data Centre | Dynamic checklist + real file upload, with duplicate-detection prompt |
| Trial Balance | FS-mapping suggestions, apply, balance-direction flags |
| GST / TDS / Payroll | Run reconciliation, view exceptions |
| Bank | Bank-vs-ledger reconciliation, challan-vs-bank mapping |
| AP / AR | Ageing, duplicate invoice detection |
| Risk Engine | Multi-category scoring, honestly shows "no data" categories |
| Exceptions | Central register, filter, sync, root-cause drawer, draft client query |
| Month-End Close | Checklist with live system-computed status |
| Working Papers | Auto-draft + prepare/review/approve sign-off |
| CARO | 21-clause tracker with sign-off, `window.prompt` for the final response text |
| IFC | Automated control tests + manual recording for the rest |
| AI Assistant | The ANSWER/DATA USED/CALCULATION/.../PROCEDURE structured format |

## What was actually verified (and the honest limit of that verification)

1. **`npm run build` succeeds with zero errors** — a real production build,
   not just "the code looks right."
2. **The dev server's API proxy was tested against the live backend**:
   started Postgres, the FastAPI server, and the Vite dev server together,
   then confirmed `curl http://127.0.0.1:5173/api/health` returns the same
   `{"status":"ok"}` as hitting the backend directly — the network wiring is
   real, not assumed.
3. **Every page's data access was manually cross-checked against the actual
   Pydantic response model** for its endpoint (not guessed field names) —
   e.g. confirmed `ControlTowerRowOut`'s `return_` field (named with a
   trailing underscore because `return` is a Python keyword) is accessed
   the same way in `Dashboard.jsx`, and that `DataCentreOut.checklist` is a
   list under a `checklist` key, not `items` or `data`.

**What this does NOT include, stated plainly**: no headless browser is
available in this environment, so no actual React rendering, click-through,
or visual verification happened. The build compiling and the network path
being real are strong signals, but they are not the same as confirming a
button click actually updates state correctly on screen. The most likely
class of remaining bug is a runtime error inside a component (e.g. a null
field a page didn't guard against) that only a real browser session would
surface — treat this as a solid, buildable starting point that needs one
real click-through session before being trusted for a live user.

## Known gaps

- **No PBC/client portal role** — the sidebar and every page assume an
  internal firm user; `CLIENT_USER` role has no dedicated UI.
- **No drill-down/side-panel drawers beyond Exceptions** — Section 104's
  full "exception drawer" pattern (assign, upload evidence, escalate) is
  only partially built; other pages show flat tables.
- **CARO's final-response entry uses a native `window.prompt`** — functional
  but not the polished textarea a real audit tool needs.
- **No Excel export button wired up** — `downloadAuditFile` exists in the
  API client but isn't called from any page yet.
- **No responsive/mobile layout** — Section 110's tablet/mobile experience
  isn't addressed; the sidebar layout is desktop-only.
- **No dark mode, saved views, bulk actions, or keyboard navigation** —
  Section 109/110's power-user features aren't built.
