# AI Audit OS — Phase 6: GST/TDS Statutory Reconciliation

The matching hierarchy (Section AZ) implemented for real: Books vs GSTR-1,
Purchase Register vs GSTR-2B (ITC), GSTR-1 vs GSTR-3B period totals, and TDS
deducted/paid/reported reconciliation with interest exposure — run against
Meridian Fashions' **real ingested invoices and bank data from Phase 4**, with
newly-uploaded GST return and TDS files deliberately engineered to contain
known mismatches, so every result could be checked against an expected answer
rather than just "did it run without erroring."

## What's implemented

| Endpoint | Purpose |
|---|---|
| `POST .../analytics/gst-reconciliation/run` | Books-vs-GSTR-1, Purchase-vs-GSTR-2B, GSTR-1-vs-GSTR-3B |
| `GET .../gst-reconciliation` | exception list, drill-down fields per Section 59 |
| `POST .../analytics/tds-reconciliation/run` | deducted/paid/reported by section, interest exposure |
| `GET .../tds-reconciliation` | TDS exception list |
| `POST .../data/upload` (extended) | now also accepts GSTR1 / GSTR2B / GSTR3B / TDS_LEDGER / TDS_CHALLAN / TDS_RETURN |

## Matching hierarchy (Section AZ) — MVP scope

- **L1**: exact `(invoice_no, gstin)` match.
- **L2/L3 fallback**: when no L1 match exists, falls back to amount (within
  ₹1 tolerance) + party name — catches the very common real-world case where
  a document number is entered inconsistently between books and the GST
  portal but the party and value agree.
- **L4-L6** (period-only fallback, fuzzy matching, AI-assisted matching with
  confidence scoring) are **not built** — every match here is either L1 or
  the L2/L3 fallback. Documented as a gap, not silently absent.

Every match and exception writes through to the actual schema built in Phase
2: `reconciliation_run` → `reconciliation_match` (with real `source_a_entity_id`
pointing at the actual `invoice` row, not a placeholder) → `reconciliation_exception`
→, for HIGH/CRITICAL risk items, `audit_exception` (the central hub from
Section 80/82) — the same chain a real working paper would later reference.

## What was actually verified end-to-end

Built the test data so every result had a known correct answer, then checked
the live API output and the database against it:

1. **Books vs GSTR-1** on 4 real invoices vs 3 uploaded GSTR-1 rows: an exact
   match, an amount mismatch (₹5,900 caught precisely), a same-amount/
   different-document-number pair correctly caught by the L2/L3 fallback
   (not just L1), and a books-only invoice correctly flagged unmatched.
   Totals: 4 processed, 2 matched, 1 partial, 1 unmatched — matches the
   hand-worked expectation exactly.
2. **Purchase Register vs GSTR-2B**: same pattern, 3 processed, 1 matched, 1
   partial (₹16,200 mismatch), 1 unmatched (an invoice entirely absent from
   2B — the classic "ITC not available" finding).
3. **GSTR-1 vs GSTR-3B**: hand-computed period totals (₹21,18,100 vs
   ₹20,59,100 for Apr-2025) came back with the exact ₹59,000 difference.
4. **TDS reconciliation**: a deliberately short-paid section (194J: deducted
   ₹41,500, paid ₹38,000) correctly flagged with interest exposure computed
   as ₹52.50 — matching the hand-calculated 1.5%/month × 1 month × ₹3,500
   shortfall exactly. The other two sections (194C, 194Q) correctly came back
   Matched.
5. **Materiality-aware hub filtering confirmed working, not just implemented**:
   with this engagement's ₹35.1L performance materiality, all five GST
   exceptions (₹5.9K–₹70.8K) correctly stayed LOW risk and did **not** create
   `audit_exception` rows, while the TDS interest exposure did (HIGH) — the
   dashboard's exception hub isn't flooded with immaterial noise, which is
   the point of materiality-based filtering, not a bug.
6. **Entity traceability confirmed real**: queried `reconciliation_match`
   directly and joined `source_a_entity_id` back to the actual `invoice`
   table — every match row resolves to a real invoice, not a generated
   placeholder (see "Bugs found" #3 below for why this needed explicit fixing).

## Bugs found by actually running this (not caught by reading the code)

1. **Same audit-trigger bug class, third occurrence.** `reconciliation_match`
   was wired into migration 010's generic audit trigger, but — like `client`,
   `engagement` (Phase 3) and `journal_line` (Phase 4) before it — has no
   `engagement_id` column, only `run_id → reconciliation_run.engagement_id`.
   Every reconciliation run 500'd until fixed with a fourth dedicated trigger
   function (`fn_log_audit_trail_reconciliation_match`, migration 016). At
   this point the pattern is clear enough to watch for proactively in any
   future table that references its engagement indirectly.
2. **Ambiguous operator type inference in raw SQL.** `values (..., $3, $3-$4, ...)`
   — arithmetic directly on two untyped bind parameters inside a VALUES list
   — raised `AmbiguousFunctionError: operator is not unique: unknown - unknown`
   from Postgres, which can't resolve which `-` overload applies without a
   type hint. Fixed with explicit casts (`$3::int - $4::int`).
3. **Traced and fixed before it could ship a real correctness bug**: the
   first draft used `gen_random_uuid()` as a placeholder for
   `reconciliation_match.source_a_entity_id`/`source_b_entity_id` instead of
   the actual invoice/gst_transaction row id — which would have silently
   broken the Evidence Graph drill-down (click a mismatch → see the actual
   source invoice) that this whole system's traceability promise depends on.
   Caught by tracing the code before running it, then confirmed fixed by
   querying the real join afterward (see verification #6 above).
4. **A real NOT NULL constraint conflict, also caught before running**: the
   fix for #3 initially still broke on the "present in GSTR-1 only" unmatched
   case, since `source_a_entity_id` is `NOT NULL` by design but that case has
   no `invoice` row at all (`side_a` is `None`). Fixed by falling back to
   whichever side actually has a real record for the "primary" slot, rather
   than relaxing the constraint or writing a fake id — every id in the table
   is still real, just not always semantically "side A."
5. **A genuine, unrelated but important correctness bug found earlier in this
   phase's ingestion work, worth restating here**: a BSR code `'0123456'`
   silently lost its leading zero because pandas auto-infers numeric columns
   on CSV load. Fixed by forcing `dtype=str` on every load and relying on
   each parser's existing explicit `pd.to_numeric()` calls for genuinely
   numeric fields — this matters specifically for Phase 6 because BSR codes,
   challan numbers, and PAN/GSTIN are exactly the kind of statutory
   identifiers that would fail silently to match against government records
   if corrupted this way.
6. **A filtering bug in the GET endpoint**: `/gst-reconciliation` initially
   returned *every* reconciliation exception for the engagement, including
   the unrelated TDS one, because it joined `reconciliation_run` without
   filtering `recon_type`. Caught by actually reading the response rather
   than just checking the HTTP status — fixed with a `recon_type LIKE 'GST_%'`
   filter.

## Known gaps / not yet built

- **L4-L6 matching** (period-only fallback, fuzzy string matching, AI-assisted
  matching with an LLM disambiguating ambiguous cases) — only L1 and a single
  L2/L3-style fallback are implemented. Real GST reconciliation needs fuzzy
  matching for genuinely messy vendor/invoice-number data more than this MVP
  provides.
- **RCM, credit/debit notes, e-invoice/e-way bill reconciliation** (Sections
  63-64) — not built; only the core Books↔GSTR-1↔GSTR-3B↔GSTR-2B chain.
- **TDS interest calculation is simplified** to a flat 1.5%/month on the
  shortfall — the real Sec 201(1A) distinguishes 1%/month (late deduction)
  from 1.5%/month (late payment), which requires knowing *which* failure
  occurred, not just that there's a shortfall. Documented as a known
  simplification in `reconciliation.py`'s docstring, not silently assumed
  correct.
- **No PBC/query auto-generation from these exceptions yet** — the
  `audit_query` table and its auto-draft workflow (Section BM) exists in the
  schema but isn't wired to fire from reconciliation exceptions automatically.
- **`match_invoice_level`'s weights/tolerance are code constants**, same
  caveat as Phase 5's risk weights — belongs in the versioned rule engine
  eventually, not hardcoded.

## Next phase

Per the roadmap: evidence management + working papers (auto-drafting a
working paper from a reconciliation run's exceptions, using the schema and
Evidence Graph edges already built), or the AI assistant layer that narrates
these deterministic results in the ANSWER/DATA USED/CALCULATION/STANDARD/
EVIDENCE/IMPLICATION/PROCEDURE format from the original spec.
