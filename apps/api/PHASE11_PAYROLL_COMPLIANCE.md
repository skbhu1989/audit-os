# AI Audit OS — Phase 11 (partial): Payroll Statutory Reconciliation + Compliance Calendar

Two of the roadmap's seven Phase 11 sub-sections, built and tested to the
same standard as everything before: PF/ESI/PT reconciliation (mirroring the
proven TDS pattern from Phase 6) and the Statutory Compliance Calendar
(Section 77), with genuine, correctly-sourced Indian statutory due-date
rules — not invented dates.

## What's implemented

| Endpoint | Purpose |
|---|---|
| `POST .../data/upload` (extended) | EMPLOYEE_MASTER, PAYROLL_REGISTER, PF_CHALLAN, ESI_CHALLAN, PT_CHALLAN |
| `POST .../analytics/payroll-reconciliation/run` | liability (payroll) vs paid (challan), by scheme and period |
| `GET .../payroll-reconciliation` | exception list |
| `POST .../compliance-calendar/generate` | generates a full FY calendar from real due-date rules, idempotent |
| `PATCH .../compliance-calendar/{id}` | record an actual filing/payment date |
| `GET .../compliance-calendar` | list with live-computed status (PENDING/OVERDUE/FILED_ON_TIME/FILED_LATE) |

## Genuine due-date rules (not invented)

GSTR-3B (20th of following month), GSTR-1 (11th), TDS payment (7th, except
March which is due 30 April — handled as an explicit special case, not the
flat rule), PF ECR+payment (15th), ESI (15th), Professional Tax (15th —
flagged as a common default since PT due dates genuinely vary by state and
this isn't authoritative for all of them). Documented in
`compliance_calendar.py`'s docstring as a starting default that belongs in
the versioned rule engine eventually, and as *not* a substitute for checking
current notifications, since due dates change and this system has no live
regulatory-change feed.

## What was actually verified end-to-end

1. **Payroll reconciliation, first pass** (before the fix below) surfaced a
   serious false-positive problem — see Bug #1.
2. **After the fix**: uploaded a deliberately engineered scenario — April
   payroll liability, paid via challan in May (the standard, correct PF/ESI
   timing) for PF and ESI, with PF short-paid by exactly ₹2,800 and ESI paid
   in full, and PT never paid at all. Result: ESI correctly shows **zero**
   exceptions (a routine, fully-compliant scenario correctly recognized as
   such), PF correctly shows exactly one exception for the ₹2,800 shortfall,
   PT correctly shows as fully unpaid. Every number matches what was
   engineered into the test data.
3. **Compliance calendar**: generated 72 items (6 statutory types × 12
   months) for a real engagement's FY, confirmed the March-TDS date lands on
   30 April (not the flat-rule 7th), confirmed idempotency (re-running
   `generate` skips all 72 existing items rather than duplicating them), and
   confirmed recording an actual filing date correctly recomputes status and
   delay days live.

## Bugs found by actually running this (not caught by reading the code)

1. **A serious false-positive bug, caught only because the test data used
   realistic dates instead of same-month toy data.** PF/ESI/PT challans are
   paid the month *after* the liability period by standard practice (due
   15th of the following month). The first version of the reconciliation
   query compared challan-payment-month labels directly against
   liability-period labels with no adjustment — so a completely normal,
   fully-paid April liability, paid on time in May, came back as **two
   separate exceptions** ("unpaid April liability" HIGH risk, and "unexplained
   May overpayment" MEDIUM risk) instead of zero. This is exactly the kind of
   bug that would generate false audit findings on routine, fully-compliant
   payroll behavior and teach an auditor to distrust the tool. Fixed by
   shifting the challan period back by one month before comparing — verified
   by rerunning against the same test data and confirming the deliberately
   correct ESI payment now shows zero exceptions while the deliberately
   short-paid PF still correctly shows its one real exception.

## Known limitations, stated honestly

- **The one-month shift is a simplification**, not full due-date-aware
  matching. A challan paid two or three months late (a genuine problem
  worth flagging) would not correctly align back to its liability period
  either — it would show as a fresh "unmatched payment," which happens to
  still surface as an exception (a good failure mode) but with a
  potentially confusing period label. A more complete implementation would
  match against a due-date window per the Compliance Calendar's actual
  rules, not a flat month-shift.
- **No 3-way reconciliation** (liability vs challan vs return/ECR) — only
  2-way (liability vs paid), unlike TDS's 3-way ledger/challan/return check.
  PF's ECR filing isn't ingested or compared separately.
- **Professional Tax due dates are a single default (15th)**, not
  state-specific — PT is a state subject in India with genuinely varying
  due dates and slab structures.

## Still not built from the original Phase 11 scope

- Income Tax / Advance Tax reconciliation (Section AV) — books vs advance
  tax vs self-assessment tax vs TDS/TCS credits vs AIS/26AS vs tax return
- MCA/ROC reconciliation (Section AY) — though `share_capital_entry` and
  `loan.roc_charge_id` exist in the schema (Phase 2) ready for this
- Cross-statutory analytics (Section BD) — GST revenue vs books vs income
  tax revenue, TDS salary vs payroll vs financial statements, etc.
- Statutory compliance score (Section 88) — the 0-100 per-statutory-type
  score with reasons, analogous to what Phase 7's risk engine did for audit
  risk categories
- Master data consistency engine (Section 84) — name/PAN/GSTIN/address
  mismatch detection across books/GST/TDS/payroll/bank/MCA/tax
- Statutory liability roll-forward (Section 75) — opening + current period
  liability − payments − adjustments = closing, compared to GL/returns/challans

## Next

Per the original roadmap, Phase 12 (CARO, IFC, financial statement review,
reporting suite) is the one remaining unbuilt phase — a fundamentally
different, more judgment-heavy kind of module than everything built so far,
worth scoping deliberately rather than rushing.
