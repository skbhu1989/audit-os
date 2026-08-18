# AI Audit OS — Intercompany Reconciliation Module

Section 33. Unlike FAR/Inventory/Loans/Investments, no schema existed for
this at all — built from scratch this phase.

## Honest scoping — read this first

The spec's "ENTITY A ↔ ENTITY B" reconciliation implies true cross-entity
matching, which needs group-structure tracking (which engagement belongs to
which group, with access to both entities' actual books) that this system
doesn't have. What's built instead: **this entity's own intercompany
ledger reconciled against an uploaded counterparty confirmation/statement**
— structurally identical to bank reconciliation (Section 54: internal
record vs. external confirmation), applied here. This is a legitimate and
common real audit procedure (intercompany confirmations are standard
practice), just not literally "two full sets of books talking to each
other." Stated in the migration's own comment and here, not glossed over.

## What's implemented

| Endpoint | Purpose |
|---|---|
| `POST .../data/upload` (extended) | `INTERCOMPANY_LEDGER` (this entity's books) and `INTERCOMPANY_CONFIRMATION` (counterparty statement) |
| `GET .../intercompany` | Full reconciliation + counterparty net-position summary |

Both dataset types reuse the same parser (`parse_intercompany_transactions`)
— a books ledger and a confirmation are structurally identical, only the
`source` tag differs, same reuse pattern as PF/ESI/PT challans sharing the
TDS challan parser back in Phase 11.

## What was actually verified end-to-end

Built test data covering all four possible match outcomes, verified each:

1. **MATCHED**: a management fee entry recorded 2 days apart in each
   entity's books (routine timing variation) — correctly matched despite
   the date difference, since it's within the matching window and the
   amount agrees exactly.
2. **MISMATCHED**: a loan recorded identically in both books except for a
   ₹2,00,000 amount difference — correctly caught as a mismatch (not
   silently matched, not silently missed), with the difference amount
   preserved exactly and a specific likely-cause classification attached.
3. **MISSING_IN_CONFIRMATION**: a shared expense entry in this entity's
   books with no counterparty confirmation anywhere near it in time —
   correctly flagged as unconfirmed.
4. **MISSING_IN_BOOKS**: a recharge the counterparty confirmed but this
   entity never recorded — correctly flagged as the reverse gap.
5. **Counterparty summary**: net books position correctly aggregated across
   all three of this entity's own ledger entries (Rs 95,50,000), independent
   of the confirmation-matching results.
6. **FX handling**: uploaded a non-INR currency during unit testing and
   confirmed the system correctly warns rather than silently converting or
   silently ignoring the mismatch — no FX conversion is performed anywhere
   in this module, by design (stated in the parser, not hidden).

## Known gaps

- **No true cross-engagement reconciliation** — see the scoping note above.
  A future phase would need a `group_id` concept linking related
  engagements and the ability to pull one engagement's ledger as the
  "confirmation" source for another, automatically.
- **No FX conversion** — non-INR amounts are used as-is with a warning, not
  converted at a period-end or transaction-date rate. A genuinely
  cross-border intercompany reconciliation needs this to be meaningful.
- **Likely-cause classification is a simple date-gap heuristic**
  (>5 days = timing difference, otherwise = recording/FX error), not a
  learned or rule-engine-driven classification the way Section 61's root
  cause module is for other exception types. Could be unified with that
  module in a future pass.
- **No confirmation-request generation** — Section 62's Management Query
  Engine isn't wired to auto-draft an intercompany confirmation request the
  way it can draft a query from a GST/TDS/AP/AR exception.
