# AI Audit OS — Phase 7: Multi-category Audit Risk Engine

Section BN's per-category risk scoring (Revenue, Receivables, Payables, Cash,
GST, TDS, Fraud Indicators, Statutory Compliance — 0-100, LOW through
CRITICAL), built on top of the real reconciliation and JE-risk data from
Phases 5-6, and verified against exact known numbers from those phases.

This closes the gap between the two "Phase 8"s — the original 12-phase
roadmap's Phase 8 (GST/TDS reconciliation) was already built as this
project's "Phase 6." Its Phase 7 (risk engine) had only the journal-level
piece done; this phase builds the multi-category rollup Section BN actually
describes.

## The one design decision that matters most here

**A category with no underlying data source returns `INSUFFICIENT_DATA`, not
a fabricated LOW score.** Section BN lists 14 risk categories; this system
has real data behind roughly half. For the other half — Inventory, Related
Parties, Going Concern, Financial Instruments, Estimates, IFC, and broad
Income Tax — there is genuinely nothing to compute from yet. Returning a
quiet "LOW" for those would be a false assurance: an auditor glancing at a
dashboard showing 14 green categories, 7 of which are actually "nobody
checked," is worse off than one showing 7 scored categories and 7 explicit
"no data" flags. The API distinguishes these with a `status` field
(`SCORED` vs `INSUFFICIENT_DATA`) rather than overloading `score: 0` to mean
two different things.

Even the *scored* categories carry an honest `data_gap_reason` where the
score is based on partial signals — e.g. Receivables is scored from
balance-direction flags and GST completeness only, explicitly noting that
ageing-based confirmation and ECL aren't part of it yet, rather than
presenting a partial signal as a complete risk assessment.

## What's implemented

`GET /engagements/{id}/risk` returns all 15 categories (8 scored + 7
insufficient-data) with:
- `score` (0-100) and `level` (LOW/MODERATE/MEDIUM/HIGH/CRITICAL) for scored categories
- `factors`: the specific data points that drove the score (explainability, Section BN's own requirement)
- `data_gap_reason`: honest about what the score does and doesn't cover
- Dashboard rollup: `scored_count`, `insufficient_data_count`, and the single highest-risk category/level

## What was actually verified end-to-end

Ran against the real Meridian Fashions engagement and cross-checked every
number against results already known from Phases 5, 6, and 10:

1. **GST**: 25.0/MODERATE from the same 5 exceptions (all LOW severity)
   verified in Phase 6/10 — confirms aggregating several LOW-severity items
   correctly produces a MODERATE category score rather than staying LOW,
   which is the intended behavior (many small issues are themselves a
   signal), not a bug.
2. **TDS**: 30.5/MODERATE, incorporating the same ₹52.50 interest exposure
   figure verified in Phase 6 — reparsed from the same source text rather
   than recomputed independently, so this dashboard cannot silently drift
   from the reconciliation it's summarizing.
3. **Fraud Indicators**: 20.0/LOW, correctly reflecting 0 HIGH/CRITICAL
   journals (matches Phase 5's dashboard exactly) and the 1 real duplicate
   vendor pair (matches Phase 10's AI assistant answer exactly).
4. **7 categories correctly returned INSUFFICIENT_DATA** with specific,
   distinct reasons — not a generic "not implemented" message.
5. **Highest-risk identification**: confirmed TDS (30.5) correctly
   outranks GST (25.0) despite both bucketing to MODERATE — see bug #2 below
   for how this was caught and fixed before it shipped wrong.

## Bugs found by actually running/tracing this

1. **A category-confusion bug, caught by tracing the data shape before
   wiring the query, not by running it and eyeballing a plausible-looking
   wrong answer.** Trial balance lines carry a coarse `fs_line` (e.g.
   "Balance Sheet — Current Assets") that Receivables, Cash, and Inventory
   all share — so filtering flagged accounts by `fs_line` alone cannot tell
   them apart. The first draft tried to distinguish them by searching flag
   *text* for the word "Receivable," which would have silently mis-routed
   or dropped signals. Fixed by using `account.note_ref` instead — a field
   Phase 5's mapping engine already sets specifically (`'Trade Receivables'`
   vs `'Cash and Bank Balances'` vs `'Inventories'`), which is exactly the
   granularity needed and was already sitting in the schema unused for this
   purpose.
2. **Tie-breaking by list order instead of score.** `highest_risk_category`
   initially picked whichever tied-at-MODERATE category happened to appear
   first in the results list (GST) rather than the one with the actually
   higher raw score (TDS, 30.5 vs 25.0) — caught by inspecting the real
   output, not by reading the comparison logic in isolation. Fixed by
   sorting on `(level_rank, score)` instead of `level_rank` alone.
3. **Cosmetic but worth fixing**: TDS's score computed to `30.525` before
   rounding — technically correct but needlessly precise for a number an
   auditor will read on a dashboard. Rounded consistently across all seven
   scoring functions.

## Known gaps / not yet built

- **7 of 15 categories have zero data source** — see the `data_gap_reason`
  field on each; this is the honest and complete list, not an
  understatement.
- **Even the 8 scored categories are partial signals**, explicitly
  documented per-category (e.g. Payables lacks a subsequent-payment-based
  unrecorded liability search; Cash lacks actual bank reconciliation
  matching — only balance-direction anomalies feed it).
- **Weights are code constants** (`SEVERITY_WEIGHT`), same caveat as every
  prior phase's scoring logic — belongs in the versioned rule engine
  eventually.
- **No historical trend** — this is a point-in-time snapshot; Section BN's
  dashboard vision implies tracking how category risk moves over the course
  of the engagement, which isn't built.

## Status of the original 12-phase roadmap

| Phase | Status |
|---|---|
| 1-6, 9, 10 | Built and tested (see respective READMEs) |
| **7 (this phase)** | **Built and tested — multi-category risk rollup** |
| 8 | Built and tested as this project's "Phase 6" (GST/TDS reconciliation) |
| 11 (PF/ESI/PT, Income Tax, MCA/ROC reconciliation, cross-statutory analytics, compliance calendar) | Not started |
| 12 (CARO, IFC, financial statement review, reporting suite) | Not started |
