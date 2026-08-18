from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, CurrentUser
from ..ai_assistant import build_duplicate_vendor_answer
from ..risk_engine import all_category_risks

router = APIRouter(prefix="/engagements/{engagement_id}/risk", tags=["risk-engine"])


class CategoryRiskOut(BaseModel):
    category: str
    status: str
    score: float | None
    level: str | None
    factors: list[str]
    data_gap_reason: str | None


class RiskDashboard(BaseModel):
    categories: list[CategoryRiskOut]
    scored_count: int
    insufficient_data_count: int
    highest_risk_category: str | None
    highest_risk_level: str | None


@router.get("", response_model=RiskDashboard)
async def get_risk_dashboard(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id = $1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        gst_exceptions = await conn.fetch(
            """select r.recon_type, e.risk_level from reconciliation_exception e
               join reconciliation_run r on r.id = e.run_id
               where r.engagement_id = $1 and r.recon_type like 'GST_%'""",
            engagement_id,
        )
        tds_exceptions = await conn.fetch(
            """select e.risk_level, r.recon_type
               from reconciliation_exception e join reconciliation_run r on r.id = e.run_id
               where r.engagement_id = $1 and r.recon_type = 'TDS_RECONCILIATION'""",
            engagement_id,
        )
        # TDS interest is embedded in the reason text (Phase 6's schema-fit
        # tradeoff, documented there) — reparse rather than re-deriving from
        # a different source, so this dashboard can't drift from the
        # reconciliation exception it's summarizing.
        tds_rows_full = await conn.fetch(
            """select e.reason from reconciliation_exception e join reconciliation_run r on r.id = e.run_id
               where r.engagement_id = $1 and r.recon_type = 'TDS_RECONCILIATION'""",
            engagement_id,
        )
        import re
        tds_dicts = []
        for row in tds_rows_full:
            m = re.search(r"interest exposure ([\d,]+\.\d+)", row["reason"])
            tds_dicts.append({"interest_exposure": float(m.group(1).replace(",", "")) if m else 0.0})

        gst_books_vs_gstr1 = [
            {"risk_level": e["risk_level"]} for e in gst_exceptions if e["recon_type"] == "GST_BOOKS_VS_GSTR1"
        ]
        gst_purchase_vs_2b_count = sum(1 for e in gst_exceptions if e["recon_type"] == "GST_PURCHASE_VS_GSTR2B")

        tb_flags = await conn.fetch(
            """select distinct on (a.id) a.fs_line, a.note_ref, t.flag from trial_balance_line t
               join account a on a.id = t.account_id
               where t.engagement_id = $1 and t.flag is not null
               order by a.id, t.as_of_date desc, t.created_at desc""",
            engagement_id,
        )
        # note_ref (set by Phase 5's mapping engine, e.g. 'Trade Receivables' /
        # 'Cash and Bank Balances' / 'Inventories') distinguishes these —
        # fs_line alone cannot, since Receivables/Cash/Inventory all share
        # the same coarse fs_line ('Balance Sheet — Current Assets'). Caught
        # by tracing the actual data shape before wiring the query, not by
        # running it and getting a wrong-but-plausible-looking result.
        revenue_flags = [r["flag"] for r in tb_flags if r["note_ref"] == "Revenue from Operations"]
        receivables_flags = [r["flag"] for r in tb_flags if r["note_ref"] == "Trade Receivables"]
        payables_flags = [r["flag"] for r in tb_flags if r["note_ref"] in ("Trade Payables", "Other Current Liabilities", "Short-term Provisions")]
        cash_flags = [r["flag"] for r in tb_flags if r["note_ref"] == "Cash and Bank Balances"]

        unmatched_sales = await conn.fetchval(
            """select count(*) from reconciliation_exception e join reconciliation_run r on r.id=e.run_id
               where r.engagement_id=$1 and r.recon_type='GST_BOOKS_VS_GSTR1' and e.return_amount is null""",
            engagement_id,
        )
        unmatched_purchase = await conn.fetchval(
            """select count(*) from reconciliation_exception e join reconciliation_run r on r.id=e.run_id
               where r.engagement_id=$1 and r.recon_type='GST_PURCHASE_VS_GSTR2B' and e.return_amount is null""",
            engagement_id,
        )
        bank_txn_count = await conn.fetchval("select count(*) from bank_transaction where engagement_id=$1", engagement_id)

        je_counts = await conn.fetchrow(
            """select count(*) filter (where risk_level in ('HIGH','CRITICAL')) as high_critical, count(*) as total
               from journal where engagement_id=$1 and risk_level is not null""",
            engagement_id,
        )
        vendors = await conn.fetch("select id, name from vendor where engagement_id=$1", engagement_id)
        dup_answer = build_duplicate_vendor_answer([dict(v) for v in vendors])
        dup_pairs = dup_answer.data_used.count(" vs ") if dup_answer else 0

        results = all_category_risks(
            gst_exceptions=[dict(e) for e in gst_exceptions],
            tds_exceptions=tds_dicts,
            gst_books_vs_gstr1_exceptions=gst_books_vs_gstr1,
            revenue_tb_flags=revenue_flags,
            receivables_tb_flags=receivables_flags, unmatched_sales_count=unmatched_sales or 0,
            payables_tb_flags=payables_flags, unmatched_purchase_count=unmatched_purchase or 0,
            cash_tb_flags=cash_flags, bank_txn_count=bank_txn_count or 0,
            high_critical_je_count=je_counts["high_critical"] or 0, total_je_count=je_counts["total"] or 0,
            duplicate_vendor_pairs=dup_pairs,
        )

    scored = [r for r in results if r.status == "SCORED"]
    level_rank = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "MODERATE": 2, "LOW": 1}
    # Tie-break same-level categories by raw score, not list order — e.g. TDS
    # (30.5) should outrank GST (25.0) even though both bucket to MODERATE.
    # Caught by inspecting real output where GST/TDS/Statutory Compliance tied
    # at MODERATE and the first-in-list (GST) won by accident, not by design.
    highest = max(scored, key=lambda r: (level_rank.get(r.level, 0), r.score or 0), default=None)

    return RiskDashboard(
        categories=[CategoryRiskOut(**r.__dict__) for r in results],
        scored_count=len(scored),
        insufficient_data_count=len(results) - len(scored),
        highest_risk_category=highest.category if highest else None,
        highest_risk_level=highest.level if highest else None,
    )
