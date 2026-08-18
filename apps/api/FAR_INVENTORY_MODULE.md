# AI Audit OS — Fixed Asset Register + Inventory Modules

Two of the previously-unbuilt domains (Sections 28/71 and 29/72). Both
`fixed_asset` and `inventory_item` tables existed since Phase 2 (migration
005) but had no ingestion path — every Data Centre checklist item for them
showed `NOT_UPLOADED` permanently. This closes that gap.

## What's implemented

| Endpoint | Purpose |
|---|---|
| `POST .../data/upload` (extended) | `FIXED_ASSET_REGISTER`, `INVENTORY_REGISTER` dataset types |
| `GET .../fixed-assets` | Per-asset depreciation consistency check + FAR-vs-GL reconciliation |
| `GET .../inventory` | Per-item valuation (cost vs NRV), ageing classification, Inventory-vs-GL reconciliation |

## Depreciation recalculation — honestly scoped

The `fixed_asset` schema stores `gross_block`/`accum_depreciation` as
running totals, not a year-by-year schedule, and has no `residual_value`
field. A precise Schedule II-compliant recalculation needs both, and this
system doesn't reproduce specific statutory useful-life tables (getting a
number wrong there would be worse than not stating it). What's actually
computed: a straightforward SLM/WDV recalculation from gross block, useful
life, and time elapsed since acquisition, compared to what's actually
recorded — flagged as **"warrants review, not a definitive error"** when
the two differ by more than 15%, never asserted as a confirmed misstatement.

## What was actually verified end-to-end

1. **FAR upload**: 4 assets uploaded, 1 correctly rejected (accumulated
   depreciation of ₹19,00,000 exceeding gross block of ₹18,00,000 — a
   genuine data error caught by validation, not silently accepted).
2. **Depreciation consistency**: FA-001 (Dell Laptops, 3-year SLM life,
   ~3.2 years elapsed) correctly flagged under-depreciated — recorded
   ₹3,54,167 vs a recalculated expected ₹7,91,239. FA-003 (Store Fixtures,
   8-year life) correctly shows **no flag** — recorded depreciation is
   within 15% of the straightforward recalculation, exactly the intended
   "don't cry wolf on routine variance" behavior.
3. **FAR-vs-GL**: correctly shows `MISMATCH` (₹44.5L FAR total vs ₹9.86Cr
   trial balance PPE) — honest, since the uploaded sample is a small
   illustrative subset of assets, not the complete register. An auditor
   uploading a genuinely partial FAR would see exactly this signal.
4. **Inventory valuation**: SKU-102 (aged 220 days, cost ₹850/unit, NRV
   ₹600/unit) correctly triggers a ₹37,500 write-down recommendation;
   SKU-103 (aged 410 days) correctly classified `OBSOLETE` with a ₹64,000
   write-down; the two normal, NRV-above-cost items correctly show no
   write-down at all.
5. **Inventory-vs-GL**: correctly shows `MISMATCH` for the same honest
   reason as FAR — a partial sample vs the full trial balance balance.

## Known gaps

- **No physical verification workflow** — `fixed_asset.physically_verified`
  exists in the schema and is surfaced in the API response, but there's no
  endpoint to actually record a verification event; it always shows `false`
  until a future phase adds that.
- **No CWIP-to-capitalized-asset tracking** — `fixed_asset.is_cwip` exists
  but isn't used by any logic yet.
- **No opening+purchases-consumption-sales=closing stock reconciliation**
  (Section 29's full formula) — only point-in-time valuation and ageing are
  checked; movement-based reconciliation needs purchase/sales register
  linkage to inventory that isn't built.
- **WDV depreciation rate is an approximation** (`1/useful_life_years`
  applied to the declining balance) in the absence of a residual value
  field — stated explicitly in the code, not hidden.
- **Impairment testing** (`fixed_asset.impairment_indicator`) exists in the
  schema but has no logic behind it.
