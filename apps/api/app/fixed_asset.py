"""
Fixed Asset Audit (Section 71): FAR ↔ GL reconciliation and depreciation
recalculation.

Honest scoping note on depreciation recalculation: this system's fixed_asset
table stores gross_block/accum_depreciation as totals, not a year-by-year
schedule, and has no residual_value field. A precise Schedule II-compliant
recalculation needs both. What's computed here is a materiality-scale
consistency check — expected cumulative depreciation over the asset's
recorded life, compared to what's actually accumulated — flagged as a
"WARRANTS REVIEW" indicator, not a precise recomputation. Real useful-life
tables (Schedule II Part C) are not reproduced here since getting specific
statutory figures wrong would be worse than not stating them.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date


@dataclass
class DepreciationFlag:
    asset_code: str | None
    description: str
    gross_block: float
    accum_depreciation: float
    expected_accum_depreciation: float | None
    flag: str | None  # None if consistent


def check_depreciation_consistency(asset: dict, as_of: date) -> DepreciationFlag:
    """asset: {'asset_code','description','gross_block','accum_depreciation',
    'useful_life_years','depreciation_method','acquisition_date','disposal_date'}."""
    gross = asset["gross_block"]
    accum = asset["accum_depreciation"]
    life = asset.get("useful_life_years")
    acq = asset.get("acquisition_date")
    method = (asset.get("depreciation_method") or "SLM").upper()

    if asset.get("disposal_date"):
        return DepreciationFlag(asset.get("asset_code"), asset["description"], gross, accum, None, None)
    if not life or life <= 0 or not acq:
        return DepreciationFlag(
            asset.get("asset_code"), asset["description"], gross, accum, None,
            "Cannot assess — missing useful life or acquisition date",
        )

    years_elapsed = max(0.0, (as_of - acq).days / 365.25)
    years_elapsed = min(years_elapsed, life)  # depreciation shouldn't exceed useful life

    if method == "WDV":
        # Approximate WDV rate absent a residual value figure: 1/life per
        # year applied to the declining balance — a simplification, not a
        # precise WDV rate derivation (which needs residual value).
        rate = 1 / life
        remaining = gross
        expected_accum = 0.0
        for _ in range(int(years_elapsed)):
            dep = remaining * rate
            expected_accum += dep
            remaining -= dep
    else:  # SLM
        expected_accum = gross * (years_elapsed / life)

    diff_pct = abs(accum - expected_accum) / gross if gross > 0 else 0
    flag = None
    if diff_pct > 0.15:  # more than 15% off a straightforward recalculation
        direction = "under-depreciated" if accum < expected_accum else "over-depreciated"
        flag = f"Recorded depreciation appears {direction} vs a straightforward {method} recalculation — warrants review, not a definitive error"

    return DepreciationFlag(asset.get("asset_code"), asset["description"], gross, accum, round(expected_accum, 2), flag)


@dataclass
class FarGlReconciliation:
    far_total: float
    gl_total: float
    difference: float
    status: str  # 'MATCHED' | 'MISMATCH' | 'NO_DATA'


def reconcile_far_to_gl(far_gross_total: float, gl_ppe_balance: float | None) -> FarGlReconciliation:
    if gl_ppe_balance is None:
        return FarGlReconciliation(far_gross_total, 0.0, far_gross_total, "NO_DATA")
    diff = round(far_gross_total - gl_ppe_balance, 2)
    status = "MATCHED" if abs(diff) < 1.0 else "MISMATCH"
    return FarGlReconciliation(far_gross_total, gl_ppe_balance, diff, status)
