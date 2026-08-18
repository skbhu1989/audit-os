# AI Audit OS — Phase 5: Trial Balance Mapping + GL/JE Risk Analytics

Rule-based FS-line mapping suggestions for the trial balance, balance-direction
sanity checks, and deterministic journal-entry risk scoring — run against the
**real data ingested in Phase 4** (Meridian Fashions' actual uploaded TB and
journals), not synthetic samples. Per the architecture doc's separation of
concerns (Section B): all of this is deterministic rule/scoring logic, not an
LLM guessing — an AI layer can narrate *why* a score is what it is later, but
the number itself comes from `app/analytics.py`.

## What's implemented

| Endpoint | Purpose |
|---|---|
| `GET /engagements/{id}/trial-balance/mapping-suggestions` | read-only preview of FS-line suggestions for every ledger |
| `POST /engagements/{id}/trial-balance/mapping-suggestions/apply` | writes suggestions above a confidence threshold — but does NOT mark them approved |
| `PATCH /engagements/{id}/accounts/{account_id}/mapping` | the actual human-approval step (sets `mapped_by`/`mapped_at`) |
| `POST /engagements/{id}/analytics/tb-flags/run` | flags TB lines whose balance direction contradicts their FS classification |
| `POST /engagements/{id}/analytics/journal-risk/run` | scores every journal (round numbers, weekend/year-end postings, management posters, reversals, suspense involvement, materiality) |
| `GET /engagements/{id}/analytics/dashboard` | TB tie-out status, risk distribution, top flagged journals, TB flags |

## Human-approval design (Section O: "require human approval for final mapping")

`apply` and `approve` are deliberately two different actions. Applying
high-confidence suggestions writes `fs_statement`/`fs_line` so the auditor can
see the system's proposal reflected in the data, but leaves `account.mapped_by`
null. Only the explicit `PATCH .../mapping` call — a human clicking approve —
sets `mapped_by`/`mapped_at`. The dashboard's `unmapped_account_count` counts
by `mapped_by IS NULL`, not by whether `fs_line` is populated, so a firm can't
accidentally treat auto-suggestions as signed-off just because the field looks
filled in.

## What was actually verified end-to-end

1. FS mapping suggestions run against Meridian's real 21 ledger accounts via
   the live API (not just unit tests) — confirmed correct classification for
   share capital, borrowings, payables, receivables, revenue, expenses, and
   the suspense accounts.
2. Applied high-confidence suggestions (21 accounts updated) and confirmed via
   direct DB query that `mapped_by` stayed `NULL` on all of them — the
   apply/approve separation actually holds, not just in the code but in the
   data.
3. Explicitly approved one account (Suspense Account) through the PATCH
   endpoint — 204, and it's the only one with `mapped_by` set afterward.
4. TB balance-direction flags ran over all 20 real TB lines — 0 flagged,
   correct, since this trial balance's balances are all on their expected
   side (no negative receivables etc. in this dataset).
5. Journal risk scoring ran over all 4 real persisted journals from Phase 4
   and produced a sensible, explainable distribution: the year-end reversal
   journal scored MEDIUM (round number + year-end + reversal), the year-end
   suspense/management-instruction journal scored MODERATE (year-end +
   suspense — see the management-poster note below), and the two ordinary
   journals scored LOW (only "posted on a weekend," which is real — 5 and 12
   April 2025 are in fact a Saturday and a Saturday).
6. The dashboard endpoint correctly aggregates all of the above: TB ties
   (₹66.08 Cr both sides), risk distribution matches the per-journal scores,
   top-10 flagged journals sorted by score descending.

## Bug found by actually running this (not caught by reading the code)

**FS mapping rule matching was first-match-wins by rule-list order, which is
fragile once a ledger name contains multiple category-suggestive words.**
"Purchase of Stock-in-Trade" contains both `"stock"` (the Inventories/Balance
Sheet rule) and `"purchase"` (the Expenses/P&L rule); because the Inventories
rule happened to appear earlier in `FS_MAPPING_RULES`, the account got
mis-classified as a Balance Sheet asset instead of a P&L expense — silently
wrong, no error thrown, only caught by actually looking at the suggestion
output for real ledger names rather than trusting the rule table by
inspection. Fixed by scanning *all* rules and preferring the longest (most
specific) matching keyword rather than the first rule in list order — verified
this also correctly improved "Cash & Bank Balances" (now matches the more
specific "bank balance" over the generic "cash").

## Known limitation surfaced by testing (not a bug, a data-model gap)

The management-poster risk factor (`MANAGEMENT_TITLES` regex on `posted_by`)
correctly did **not** fire for the real ingested journal posted by "S. Kapoor"
— because the actual source data has no role/title information, unlike an
earlier synthetic mockup that used "S. Kapoor (CFO)". Two ways to close this
for real firms: either require source systems to export a role/title with the
poster name, or join `journal.posted_by` against `app_user.full_name` /
`engagement_team.engagement_role` where the poster happens to be a known
system user. Neither is built yet — flagging honestly rather than silently
scoring on data the system doesn't actually have.

## Known gaps / not yet built

- **FS_MAPPING_RULES is a hardcoded Python list**, not yet stored in the
  versioned `rule`/`rule_version` tables from Phase 2's Rule Engine design.
  Firms will want to customize/extend their own mapping vocabulary — that
  belongs in the DB-backed rule engine, not a code constant, before this is
  used on a second real client with different naming conventions.
- **No current/non-current split** — TB mapping classifies "Balance Sheet —
  Non-current Assets" vs "Current Assets" etc., but the underlying rules don't
  yet reason about loan maturity, asset useful life, or similar signals to
  place an account correctly when that distinction is genuinely ambiguous
  from the ledger name alone.
- **TB balance-direction flags don't yet consider materiality** — every
  direction anomaly is flagged regardless of size; in a real engagement,
  filtering to only flag anomalies above the clearly-trivial threshold would
  cut noise.
- **Risk weights are a fixed constant dict**, same caveat as the FS mapping
  rules — belongs in the versioned rule engine so a firm can tune sensitivity
  without a code change.

## Next phase

Phase 6 per the roadmap is GST/TDS reconciliation — and can now run against
the real `invoice` (sales/purchase register) and `bank_transaction` data
ingested in Phase 4, the same way this phase ran against real TB/journal data
instead of synthetic samples.
