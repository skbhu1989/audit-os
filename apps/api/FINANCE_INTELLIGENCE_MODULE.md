# AI Audit OS — Finance Intelligence Module

A deliberately narrow, honest slice of the "Universal Finance & Accounting
Intelligence Engine" spec. Given the spec's own explicit requirement
(Section 51: no black box — every finding must show FACT/SOURCE DATA/RULE/
ANALYSIS/CONCLUSION/CONFIDENCE/ACTION) and this build's established
discipline (no LLM call, no fabricated trend data), the scope here is four
features that are genuinely computable from data already in the system:

| Feature | Section | Endpoint |
|---|---|---|
| Daily Finance Briefing | 39 | `GET .../finance-briefing` |
| Vendor/Customer Master Data Intelligence | 27-28 | `GET .../finance-intelligence/master-data` |
| Fixed Asset Intelligence (repairs vs capital) | 23 | `GET .../finance-intelligence/capitalization-review` |
| Accrual Gap Calculator | 21 | `POST .../finance-intelligence/accrual-gap` |

## What's deliberately NOT attempted, and why

**Revenue/margin trend analysis** — needs period-over-period data; this
system holds one trial balance snapshot per engagement. The Finance
Briefing honestly returns `INSUFFICIENT_DATA` for both fields rather than
fabricating a trend from a single data point.

**True automatic accrual detection** (deriving the "expected annual amount"
from historical trend) — the spec's own worked example uses a *known*
reference figure ("Annual audit fee = Rs 12 lakh"), not a derived one. This
system has no multi-year GL history to derive that figure from (Meridian
Fashions has a handful of journal entries spanning a few months). Built
instead: an honest calculator matching the spec's own example exactly —
the user supplies the known expected figure, the system computes the gap.

## What was actually verified end-to-end

1. **Master Data Intelligence — genuinely new detection confirmed, and it
   cross-validated an old finding**: uploaded a vendor master with a
   deliberate same-PAN-different-name pair (Prime Textile Solutions / PTS
   Fabrics) — correctly caught, HIGH confidence. It also **independently
   re-confirmed** the "ABC Traders"/"ABC Trader's Co" pair first found by
   Phase 10's *name-similarity* detector — this time via shared GSTIN, a
   completely different signal. Two independent methods agreeing on the
   same real duplicate is a meaningful cross-check, not a coincidence to
   wave away.
2. **Capitalization review**: uploaded a journal with one genuinely large
   (Rs 18.5L) entry to "Repairs and Maintenance" with a narration
   ("machinery enhancement and capacity upgrade") that a human would
   immediately flag, plus one small routine entry (Rs 18,000, AC servicing).
   Correctly flagged only the large one.
3. **Accrual Gap Calculator**: first verified against the spec's own worked
   example exactly (Rs 12L expected, Rs 8L booked → Rs 4L gap, matched to
   the rupee). Then verified against Meridian's real Finance Costs balance
   (Rs 78L booked vs Rs 1.2Cr pro-rated expectation → Rs 42L gap).
4. **Daily Finance Briefing**: pulled real critical-exception counts (9),
   reconciliation issue counts (4), real AR total (Rs 21.83L), and correctly
   surfaced the three highest-priority real exceptions as recommended
   actions — all reused from engines already built and tested in prior
   phases, nothing recomputed from scratch.

## Two real bugs found by testing against actual data, not by reading the code

1. **Capitalization review initially returned nothing at all.** The query
   required `account.fs_statement = 'PROFIT_AND_LOSS'`, but a ledger
   auto-created purely by a journal upload (never gone through the Trial
   Balance mapping/approval flow from Phase 5) defaults to
   `fs_statement = 'UNMAPPED'` — so the very accounts most likely to need
   this kind of unreviewed-data check were silently excluded by requiring
   them to already be formally reviewed. Fixed by dropping the FS-statement
   requirement entirely: the repair-keyword match on the ledger *name* is
   already the meaningful filter, and a "Repairs and Maintenance"-named
   account is an expense account regardless of its formal mapping status.
2. **Accrual gap calculator showed a trivial Rs 0 booked** for Meridian's
   real Finance Costs ledger, because it only summed `journal_line` rows
   (transaction-level detail) — and zero of Meridian's Finance Costs balance
   exists as journal-level detail; it's a trial-balance-only figure from
   Phase 4's original upload. Fixed by querying the trial balance first (the
   authoritative period-end position) and falling back to journal detail
   only when no TB data exists for that ledger — surfaced the real Rs 78L
   figure and a meaningful Rs 42L gap instead of a meaningless zero.

## Known gaps

- **Master Data Intelligence only checks PAN/GSTIN/bank account** — the
  spec's fuller vision (same registered address, same authorized signatory,
  same phone/email) isn't checked; this system doesn't ingest those fields
  for vendors/customers.
- **Capitalization review's keyword list is small** (repair/maintenance/
  renovation/refurbish) — a real deployment would want a larger, tunable
  vocabulary, ideally in the versioned rule engine rather than a code
  constant (the same caveat noted for every rule-based module since Phase 5).
- **The Daily Finance Briefing has no real "documents pending" signal beyond
  the Data Centre's required-dataset checklist** — Section 39's fuller
  vision (pending client document requests, unanswered queries) exists in
  the `audit_query` table from Phase 9 but isn't pulled into this briefing yet.
- **No CFO scenario analysis, teaching mode, or natural-language query
  interface beyond Phase 10's existing deterministic AI Assistant** — the
  broader "Universal Finance & Accounting Intelligence Engine" vision in
  this spec is much larger than the four features built here; this is a
  deliberately narrow, honestly-scoped slice, not the full spec.
