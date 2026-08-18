# AI Audit OS — API & Integration Layer

Built per the new integration-layer specification, and its own explicit,
repeated instruction (Section 44, "critical") shaped everything here:
**never fake a live connection**. This sandbox has zero real GST/TDS/MCA/
Bank/Tally/Zoho credentials. So this phase does not simulate connectors
that don't exist — it builds the honest **integration abstraction layer**
(a real connector registry reporting genuine status) plus two **generic
APIs** that give real, unified access to work already built across every
prior phase: **Universal Import** and **Universal Reconciliation**.

## What's implemented

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/integrations` | Integration Centre — every provider's real status, classification, and reasoning |
| `POST /api/v1/integrations/{id}/test` | Always honestly reports `NOT_CONNECTED` — never simulates success |
| `POST /api/v1/integrations/{id}/connect` | Honest `501` — no fake OAuth/API-key flow |
| `POST /api/v1/imports` | Universal Import (Section 22) — generic wrapper reusing the real, already-tested upload logic |
| `GET /api/v1/imports` / `/{batch_id}` | Import batch listing/detail in the spec's status vocabulary |
| `GET /api/v1/reconciliation/types` | Documents exactly what the universal endpoint dispatches to |
| `POST /api/v1/reconciliation` | Universal Reconciliation (Section 28) — dispatches to the real GST/TDS/Payroll/Bank/Challan/FAR/Inventory/Loans/Investments/Intercompany engines |

## The core design choice: reuse, not reimplementation

Both universal endpoints call the actual existing route-handler functions
directly (`upload_dataset`, `run_gst_reconciliation`, `get_bank_reconciliation`,
etc.) with explicit arguments, bypassing only FastAPI's HTTP-layer parameter
binding, never the real parsing/validation/persistence/matching logic
underneath. This is Section 55's "do not create duplicate systems" principle
applied literally: there is exactly one GST reconciliation engine in this
codebase, callable two ways now — not two engines that could silently drift
apart.

## The Integration Registry — honest classification, not guesswork

Every provider named in the spec is seeded with a real classification and a
stated reason (Section 2's "never claim an API is free unless verified"):

| Provider | Classification | Why |
|---|---|---|
| GST Portal | NOT_PUBLICLY_AVAILABLE | Requires paid GSP/ASP registration, not a free public API |
| TRACES (TDS) | GOVERNMENT_AUTHENTICATED | Login-only, no third-party API |
| Income Tax / AIS | GOVERNMENT_AUTHENTICATED | Same |
| MCA Portal | GOVERNMENT_AUTHENTICATED | No free public API; paid resellers only |
| Bank / Account Aggregator | THIRD_PARTY_PAID | AA licensing has real fees |
| Tally | FREE | Genuinely free local XML/HTTP interface — but needs the user's own Tally instance, unreachable from this sandbox |
| Zoho Books | FREE_WITH_LIMITS | Real OAuth2 API exists, free tier — needs a registered OAuth app this environment doesn't have |
| OCR | OPTIONAL | Cloud options are paid/limited; a free local option (Tesseract) exists but isn't wired in |

Every single one shows `status: NOT_CONNECTED`. None are faked.

## What was actually verified end-to-end

1. **Integration Centre**: confirmed live — all 8 providers correctly show
   NOT_CONNECTED, `test` correctly refuses to simulate success and returns
   the real classification reason plus the fallback path, `connect`
   correctly returns 501 rather than a fake OAuth redirect.
2. **Universal Import — genuine reuse confirmed, not just claimed**: uploaded
   a real loan register file through `/api/v1/imports` with the generic
   `data_type=loan`, then confirmed via the actual Loans engine
   (`GET /engagements/{id}/loans`) that the new loan genuinely landed in the
   real `loan` table and the borrowings total updated correctly
   (Rs 8.2Cr -> Rs 8.5Cr) — proof the generic endpoint isn't a facade that
   silently drops data, it's calling the same code path.
3. **Ambiguous/unbuilt data_type handling**: `data_type=gst` with no
   `subtype` correctly 400s listing the valid options; `data_type=share_capital`
   (genuinely not built) correctly 501s rather than silently accepting and
   discarding the file.
4. **Universal Reconciliation — genuine reuse confirmed via matching
   numbers**: dispatching `reconciliation_type=TDS` through the new generic
   endpoint returned exactly the same figures (1 exception, Rs 52.50
   interest exposure) already verified independently in Phases 6 and 12 —
   if this were a reimplementation instead of a real dispatch, there'd be no
   guarantee the numbers would match this precisely.
5. **CHALLAN's required-param handling**: correctly 400s with a clear
   message when `param` is missing, correctly dispatches and returns real
   data (3 challan mappings) when provided.

## A bug caught before it ran, worth stating plainly

Calling `get_challan_mapping` directly (to reuse its logic) also bypasses
FastAPI's own `Query(..., pattern="^(GST|TDS|PF|ESI|PT)$")` validation for
`statutory_type` — that validation only runs through the HTTP request-parsing
layer, not on a direct Python call. Without an explicit check, an invalid
value would only be caught by a raw Postgres enum error bubbling up as a 500,
not a clean 400. Fixed by adding the same validation explicitly in the
dispatcher before calling through — a general lesson about this whole
reuse-by-direct-call pattern: it reuses the *logic*, but not automatically
the *HTTP-layer validation* that framework decorators normally provide.

## Known gaps — stated completely

- **No real external connector is live** — by design, per Section 44. Every
  "Phase 5-11" item in the spec's own priority list (GST/TDS/Bank/Income-tax/
  Tally/OCR/MCA live integration) remains NOT_CONNECTED, correctly.
- **No async job queue** (Section 34) — imports still process synchronously
  inline, same limitation noted since Phase 4.
- **No caching layer** (Section 32) — moot while no live API calls exist to
  cache, but also not built for future use.
- **No rate limiting, retry/backoff, or circuit breaker** (Sections 31/33) —
  same reasoning; nothing to rate-limit yet, but the abstraction for it
  isn't built either.
- **No webhook endpoint** (Section 46) — no provider to receive webhooks from.
- **No OpenAPI-level documentation beyond FastAPI's automatic `/docs`**
  (Section 45) — FastAPI generates this automatically for every endpoint in
  this codebase already; no additional hand-written API docs were produced.
- **Universal Import's data-type map doesn't cover `tax` or `share_capital`**
  — both genuinely have no ingestion type built anywhere in this system yet,
  correctly surfaced as 501, not silently mapped to something incorrect.
- **No import versioning/diff (Section 26)** — re-uploading the same dataset
  type triggers the existing ASK/REPLACE/APPEND/CANCEL flow (Pre-Audit
  Module), but there's no V1/V2/V3 comparison view showing ADDED/REMOVED/
  MODIFIED/UNCHANGED between versions.
- **The response envelope (Section 49/50) is scoped to the new endpoints
  only** — the ~30 existing routers built across prior phases return their
  original response shapes, unchanged, per the "do not rebuild existing
  functionality" principle. Retrofitting the envelope onto all of them would
  be a large, separately-scoped change.
