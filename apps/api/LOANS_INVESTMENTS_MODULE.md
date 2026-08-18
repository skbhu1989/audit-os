# AI Audit OS — Loans & Investments Modules

Two more previously-unbuilt domains (Sections 31/84 and 32), following the
same pattern as FAR/Inventory: existing schema from Phase 2 (migration 005),
no ingestion path until now.

## What's implemented

| Endpoint | Purpose |
|---|---|
| `POST .../data/upload` (extended) | `LOAN_REGISTER`, `INVESTMENT_REGISTER` dataset types |
| `GET .../loans` | Repayment default detection, interest consistency, Loans-vs-GL reconciliation |
| `GET .../investments` | Fair value staleness, impairment indicator, Investments-vs-GL reconciliation |

## The CARO integration — closing a gap flagged since Phase 12

Loan data is the first this system has ever had, so `caro.py` now drafts
**clause (ix) Repayment of Borrowings** for real — it's been sitting as
`INSUFFICIENT_DATA` since Phase 12's CARO module was first built. Verified
live: after uploading a loan register with one genuinely overdue director
loan, re-running CARO init correctly promoted clause (ix) to `DATA_BACKED`
and drafted a response citing the exact lender, exact overdue duration (821
days), and exact outstanding balance — all pulled from the real Loans
module output, not fabricated.

## What was actually verified end-to-end

1. **Loan register upload**: 4 loans loaded cleanly, including a deliberately
   overdue director loan (matured 31-Dec-2023, this engagement's reporting
   date is 31-Mar-2026).
2. **Default detection**: correctly flagged only the overdue loan (821 days
   past maturity) — the other two borrowings (future maturity) and the one
   lending arrangement (direction ≠ BORROWING, correctly excluded from
   default checks entirely) all correctly show no flag.
3. **Interest consistency**: no false positives — none of the three
   borrowings' expected annual interest exceeded the engagement's real
   recorded Finance Costs, so all correctly show no flag (this check exists
   specifically to catch the *opposite* case: a loan whose implied interest
   is implausibly large relative to what's actually expensed).
4. **Loans-vs-GL and Investments-vs-GL**: both correctly show `MISMATCH` —
   honest, since these are small illustrative registers, not complete ones
   matching the full trial balance.
5. **Investment flags**: the missing-fair-value item and the 60%-below-cost
   item both correctly flagged; the healthy mutual fund investment correctly
   shows zero flags.
6. **CARO clause (ix) integration**: confirmed live — re-running CARO init
   after the loan upload correctly promoted the clause from
   `INSUFFICIENT_DATA` to `DATA_BACKED`, with the draft text citing the real
   overdue loan by name, exact day count, and exact balance.

## Bug found and fixed before this ever ran

While wiring the CARO clause (ix) integration, I wrote a placeholder
expression for the "as of" date — `eng["performance_materiality"] and
date.today() or date.today()` — nonsensical leftover from copy-paste, and
worse, `eng` in that query only selected `performance_materiality`, not
`reporting_date`, which the loan default check actually needs (using
`date.today()` instead of the engagement's actual reporting date would have
silently used the wrong reference date for every future or past-dated
engagement). Caught by reading the code before running it, not by a test
failure — fixed by adding `reporting_date` to the query and using it
directly.

## Known gaps

- **Interest consistency can't attribute finance cost to a specific loan**
  — the GL doesn't break Finance Costs out per lender, so this only catches
  the case where one loan's expected interest alone exceeds the *total*
  recorded finance cost, not more granular mismatches.
- **No Section 185/186 compliance check** (CARO clause iv, loans/investments/
  guarantees to related parties under Companies Act sections) — the
  `loan.is_related_party` and `investment.is_subsidiary_associate_jv` fields
  exist in the schema but have no logic behind them yet, since related-party
  identification itself isn't built.
- **No covenant tracking** — `loan.security_details` is a free-text field
  with no structured covenant data or compliance checking.
- **Investment impairment flag is a threshold heuristic** (20% below cost),
  not an Ind AS 109-compliant impairment model — explicitly worded as
  "consider whether," never asserted as a required write-down.
