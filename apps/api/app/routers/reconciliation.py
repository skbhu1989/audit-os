import json
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, require_roles, CurrentUser
from ..reconciliation import (
    match_invoice_level, classify_gst_reason, gst_risk_level,
    reconcile_period_totals, reconcile_tds, reconcile_payroll_statutory,
)

router = APIRouter(prefix="/engagements/{engagement_id}", tags=["reconciliation"])
WRITE_ROLES = ("FIRM_ADMIN", "PARTNER", "MANAGER", "SENIOR")


async def _load_invoice_side(conn, engagement_id, direction):
    rows = await conn.fetch(
        """select i.id, i.invoice_no, i.invoice_date, i.total_value as amount,
                  coalesce(v.name, c.name) as party, coalesce(v.gstin, c.gstin) as gstin
           from invoice i left join vendor v on v.id = i.vendor_id
                           left join customer c on c.id = i.customer_id
           where i.engagement_id = $1 and i.direction = $2""",
        engagement_id, direction,
    )
    return [dict(r) for r in rows]


async def _load_gst_return_side(conn, engagement_id, source):
    rows = await conn.fetch(
        """select id, document_no as invoice_no, party_name as party, gstin,
                  (taxable_value + cgst + sgst + igst + cess) as amount
           from gst_transaction where engagement_id = $1 and source = $2 and document_no is not null""",
        engagement_id, source,
    )
    return [dict(r) for r in rows]


async def _get_engagement_materiality(conn, engagement_id):
    row = await conn.fetchrow("select performance_materiality from engagement where id = $1", engagement_id)
    return float(row["performance_materiality"]) if row and row["performance_materiality"] else None


async def _persist_matches(conn, run_id, engagement_id, matches, recon_type, side_a_label, side_b_label, materiality):
    matched = sum(1 for m in matches if m.status == "MATCHED")
    partial = sum(1 for m in matches if m.status == "PARTIALLY_MATCHED")
    unmatched = sum(1 for m in matches if m.status == "UNMATCHED")

    await conn.execute(
        """update reconciliation_run set total_records=$1, matched_count=$2, partial_count=$3, unmatched_count=$4
           where id = $5""",
        len(matches), matched, partial, unmatched, run_id,
    )

    for m in matches:
        # source_a_entity_id is NOT NULL by schema design (a match row must
        # always anchor to a real record) — but our matching can produce an
        # UNMATCHED result where only side_b has data (a GSTR-1 entry with no
        # books counterpart). Falling back to whichever side is actually
        # populated keeps every id real (never a placeholder), rather than
        # violating the constraint or writing a fake UUID.
        if m.side_a is not None:
            a_type, a_id = "invoice", m.side_a["id"]
            b_type, b_id = ("gst_transaction", m.side_b["id"]) if m.side_b is not None else (None, None)
        else:
            a_type, a_id = "gst_transaction", m.side_b["id"]
            b_type, b_id = (None, None)

        match_row = await conn.fetchrow(
            """insert into reconciliation_match (run_id, source_a_entity_type, source_a_entity_id,
                                                    source_b_entity_type, source_b_entity_id,
                                                    match_level, match_status, confidence_score,
                                                    matching_factors, amount_a, amount_b)
               values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
               returning id""",
            run_id, a_type, a_id, b_type, b_id, m.match_level, m.status, m.confidence, m.matching_factors,
            m.side_a["amount"] if m.side_a else None, m.side_b["amount"] if m.side_b else None,
        )

        if m.status == "MATCHED":
            continue  # only write exception rows for anything not a clean match

        reason = classify_gst_reason(m, side_a_label, side_b_label)
        risk = gst_risk_level(m.difference, materiality)
        party = (m.side_a or m.side_b or {}).get("party")
        gstin = (m.side_a or m.side_b or {}).get("gstin")
        doc_no = (m.side_a or m.side_b or {}).get("invoice_no")

        exc_row = await conn.fetchrow(
            """insert into reconciliation_exception (run_id, match_id, gstin, document_no, party_name,
                                                        books_amount, return_amount, difference, reason,
                                                        risk_level, suggested_action)
               values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) returning id""",
            run_id, match_row["id"], gstin, doc_no, party,
            m.side_a["amount"] if m.side_a else None, m.side_b["amount"] if m.side_b else None,
            m.difference, reason, risk,
            "Raise a client query with supporting documentation for this difference",
        )

        if risk in ("HIGH", "CRITICAL"):
            audit_exc = await conn.fetchrow(
                """insert into audit_exception (engagement_id, source_type, source_id, compliance_type,
                                                  fs_area, amount, difference, reason, risk_level,
                                                  recommended_action, status)
                   values ($1,'RECONCILIATION',$2,'GST','GST',$3,$4,$5,$6,$7,'OPEN') returning id""",
                engagement_id, exc_row["id"], m.difference, m.difference, reason, risk,
                f"Investigate {recon_type} difference of {abs(m.difference):,.2f} for document {doc_no or '(unmatched)'}",
            )
            await conn.execute(
                "update reconciliation_exception set audit_exception_id = $1 where id = $2",
                audit_exc["id"], exc_row["id"],
            )


class GstReconciliationRunResult(BaseModel):
    books_vs_gstr1: dict
    purchase_vs_gstr2b: dict
    gstr1_vs_gstr3b_periods_flagged: int


@router.post("/analytics/gst-reconciliation/run", response_model=GstReconciliationRunResult)
async def run_gst_reconciliation(engagement_id: UUID, user: CurrentUser = Depends(require_roles(*WRITE_ROLES))):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id = $1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")
        materiality = await _get_engagement_materiality(conn, engagement_id)

        # --- Books (sales) vs GSTR-1 ---
        books_sales = await _load_invoice_side(conn, engagement_id, "SALES")
        gstr1 = await _load_gst_return_side(conn, engagement_id, "GSTR1")
        run1 = await conn.fetchrow(
            """insert into reconciliation_run (engagement_id, recon_type, period, source_a_desc, source_b_desc, run_by)
               values ($1,'GST_BOOKS_VS_GSTR1','ALL','Books (Sales Register)','GSTR-1',$2) returning id""",
            engagement_id, user.user_id,
        )
        matches1 = match_invoice_level(books_sales, gstr1)
        await _persist_matches(conn, run1["id"], engagement_id, matches1, "Books vs GSTR-1", "Books", "GSTR-1", materiality)

        # --- Purchase Register vs GSTR-2B (ITC) ---
        books_purchase = await _load_invoice_side(conn, engagement_id, "PURCHASE")
        gstr2b = await _load_gst_return_side(conn, engagement_id, "GSTR2B")
        run2 = await conn.fetchrow(
            """insert into reconciliation_run (engagement_id, recon_type, period, source_a_desc, source_b_desc, run_by)
               values ($1,'GST_PURCHASE_VS_GSTR2B','ALL','Purchase Register','GSTR-2B',$2) returning id""",
            engagement_id, user.user_id,
        )
        matches2 = match_invoice_level(books_purchase, gstr2b)
        await _persist_matches(conn, run2["id"], engagement_id, matches2, "Purchase Register vs GSTR-2B", "Purchase Register", "GSTR-2B", materiality)

        # --- GSTR-1 vs GSTR-3B period totals ---
        gstr1_totals_rows = await conn.fetch(
            """select period, sum(taxable_value + cgst + sgst + igst + cess) as total
               from gst_transaction where engagement_id = $1 and source = 'GSTR1' group by period""",
            engagement_id,
        )
        gstr3b_totals_rows = await conn.fetch(
            """select period, sum(taxable_value + cgst + sgst + igst + cess) as total
               from gst_transaction where engagement_id = $1 and source = 'GSTR3B' group by period""",
            engagement_id,
        )
        gstr1_totals = {r["period"]: float(r["total"]) for r in gstr1_totals_rows}
        gstr3b_totals = {r["period"]: float(r["total"]) for r in gstr3b_totals_rows}
        period_exceptions = reconcile_period_totals(gstr1_totals, gstr3b_totals, materiality)

        run3 = await conn.fetchrow(
            """insert into reconciliation_run (engagement_id, recon_type, period, source_a_desc, source_b_desc, run_by,
                                                  total_records, matched_count, partial_count, unmatched_count)
               values ($1,'GST_GSTR1_VS_GSTR3B','ALL','GSTR-1','GSTR-3B',$2,$3,$3::int-$4::int,0,$4) returning id""",
            engagement_id, user.user_id, len(gstr1_totals) + len(gstr3b_totals), len(period_exceptions),
        )
        for pe in period_exceptions:
            exc_row = await conn.fetchrow(
                """insert into reconciliation_exception (run_id, period, books_amount, return_amount, difference, reason, risk_level, suggested_action)
                   values ($1,$2,$3,$4,$5,$6,$7,$8) returning id""",
                run3["id"], pe.period, pe.books_amount, pe.return_amount, pe.difference, pe.reason, pe.risk,
                "Obtain the client's GSTR-1 vs GSTR-3B reconciliation statement for this period",
            )
            if pe.risk in ("HIGH", "CRITICAL"):
                await conn.execute(
                    """insert into audit_exception (engagement_id, source_type, source_id, compliance_type, period,
                                                       fs_area, difference, reason, risk_level, recommended_action, status)
                       values ($1,'RECONCILIATION',$2,'GST',$3,'GST',$4,$5,$6,$7,'OPEN')""",
                    engagement_id, exc_row["id"], pe.period, pe.difference, pe.reason, pe.risk,
                    f"Investigate GSTR-1/3B turnover gap of {abs(pe.difference):,.2f} for {pe.period}",
                )

    return GstReconciliationRunResult(
        books_vs_gstr1={"total": len(matches1), "matched": sum(1 for m in matches1 if m.status == "MATCHED"),
                         "unmatched": sum(1 for m in matches1 if m.status == "UNMATCHED"),
                         "partial": sum(1 for m in matches1 if m.status == "PARTIALLY_MATCHED")},
        purchase_vs_gstr2b={"total": len(matches2), "matched": sum(1 for m in matches2 if m.status == "MATCHED"),
                             "unmatched": sum(1 for m in matches2 if m.status == "UNMATCHED"),
                             "partial": sum(1 for m in matches2 if m.status == "PARTIALLY_MATCHED")},
        gstr1_vs_gstr3b_periods_flagged=len(period_exceptions),
    )


class GstExceptionOut(BaseModel):
    recon_type: str
    period: str | None
    gstin: str | None
    document_no: str | None
    party_name: str | None
    books_amount: float | None
    return_amount: float | None
    difference: float | None
    reason: str
    risk_level: str
    suggested_action: str | None


@router.get("/gst-reconciliation", response_model=list[GstExceptionOut])
async def list_gst_exceptions(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        rows = await conn.fetch(
            """select r.recon_type, e.period, e.gstin, e.document_no, e.party_name,
                      e.books_amount, e.return_amount, e.difference, e.reason, e.risk_level, e.suggested_action
               from reconciliation_exception e join reconciliation_run r on r.id = e.run_id
               where r.engagement_id = $1 and r.recon_type like 'GST_%'
               order by
                 case e.risk_level when 'CRITICAL' then 1 when 'HIGH' then 2 when 'MEDIUM' then 3 when 'MODERATE' then 4 else 5 end""",
            engagement_id,
        )
    return [GstExceptionOut(**dict(r)) for r in rows]


# ---------- TDS reconciliation ----------

class TdsReconciliationRunResult(BaseModel):
    sections_analyzed: int
    exceptions_found: int
    total_interest_exposure: float


@router.post("/analytics/tds-reconciliation/run", response_model=TdsReconciliationRunResult)
async def run_tds_reconciliation(engagement_id: UUID, user: CurrentUser = Depends(require_roles(*WRITE_ROLES))):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id = $1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        deducted_rows = await conn.fetch(
            "select section, sum(tds_amount) as total from tds_transaction where engagement_id=$1 and source='LEDGER' group by section",
            engagement_id,
        )
        reported_rows = await conn.fetch(
            "select section, sum(tds_amount) as total from tds_transaction where engagement_id=$1 and source='RETURN' group by section",
            engagement_id,
        )
        paid_rows = await conn.fetch(
            "select tax_head as section, sum(amount) as total from challan where engagement_id=$1 and statutory_type='TDS' group by tax_head",
            engagement_id,
        )
        deducted = {r["section"]: float(r["total"]) for r in deducted_rows}
        reported = {r["section"]: float(r["total"]) for r in reported_rows}
        paid = {r["section"]: float(r["total"]) for r in paid_rows}

        results = reconcile_tds(deducted, paid, reported)

        run = await conn.fetchrow(
            """insert into reconciliation_run (engagement_id, recon_type, period, source_a_desc, source_b_desc, run_by,
                                                  total_records, matched_count, unmatched_count)
               values ($1,'TDS_RECONCILIATION','ALL','TDS Ledger','Challan/Return',$2,$3,$4,$5) returning id""",
            engagement_id, user.user_id, len(results),
            sum(1 for r in results if r.status == "Matched"),
            sum(1 for r in results if r.status != "Matched"),
        )

        exceptions_found = 0
        total_interest = 0.0
        for r in results:
            if r.status == "Matched":
                continue
            exceptions_found += 1
            total_interest += r.interest_exposure
            risk = "HIGH" if r.interest_exposure > 0 else "MEDIUM"
            reason_text = f"{r.status}" + (f" — estimated interest exposure {r.interest_exposure:,.2f}" if r.interest_exposure else "")
            exc_row = await conn.fetchrow(
                """insert into reconciliation_exception (run_id, document_no, books_amount, return_amount, difference,
                                                            reason, risk_level, suggested_action)
                   values ($1,$2,$3,$4,$5,$6,$7,$8) returning id""",
                run["id"], r.section, r.deducted, r.paid, round(r.deducted - r.paid, 2),
                reason_text, risk, "Recompute interest exposure and confirm subsequent payment/revised filing",
            )
            audit_exc = await conn.fetchrow(
                """insert into audit_exception (engagement_id, source_type, source_id, compliance_type,
                                                   fs_area, difference, potential_interest, reason, risk_level,
                                                   recommended_action, status)
                   values ($1,'RECONCILIATION',$2,'TDS','TDS',$3,$4,$5,$6,$7,'OPEN') returning id""",
                engagement_id, exc_row["id"], round(r.deducted - r.paid, 2), r.interest_exposure, reason_text, risk,
                f"Section {r.section}: {reason_text}",
            )
            await conn.execute(
                "update reconciliation_exception set audit_exception_id = $1 where id = $2",
                audit_exc["id"], exc_row["id"],
            )

    return TdsReconciliationRunResult(
        sections_analyzed=len(results), exceptions_found=exceptions_found, total_interest_exposure=round(total_interest, 2)
    )


class TdsExceptionOut(BaseModel):
    section: str
    deducted: float | None
    paid: float | None
    reason: str
    risk_level: str


@router.get("/tds-reconciliation", response_model=list[TdsExceptionOut])
async def list_tds_exceptions(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        rows = await conn.fetch(
            """select e.document_no as section, e.books_amount as deducted, e.return_amount as paid,
                      e.reason, e.risk_level
               from reconciliation_exception e join reconciliation_run r on r.id = e.run_id
               where r.engagement_id = $1 and r.recon_type = 'TDS_RECONCILIATION'
               order by e.risk_level""",
            engagement_id,
        )
    return [TdsExceptionOut(**dict(r)) for r in rows]


# ---------- PF / ESI / PT (payroll statutory) reconciliation ----------

LIABILITY_COLUMNS = {
    "PF": "pf_employee + pf_employer",
    "ESI": "esi_employee + esi_employer",
    "PT": "pt_amount",
}


class PayrollReconciliationRunResult(BaseModel):
    scheme: str
    periods_analyzed: int
    exceptions_found: int
    total_unpaid: float


@router.post("/analytics/payroll-reconciliation/run", response_model=list[PayrollReconciliationRunResult])
async def run_payroll_reconciliation(engagement_id: UUID, user: CurrentUser = Depends(require_roles(*WRITE_ROLES))):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select 1 from engagement where id = $1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")

        out = []
        for scheme, liability_expr in LIABILITY_COLUMNS.items():
            liability_rows = await conn.fetch(
                f"select period, sum({liability_expr}) as total from payroll_line "
                f"where engagement_id=$1 group by period",
                engagement_id,
            )
            # PF/ESI due dates fall on the 15th of the FOLLOWING month by
            # standard practice, so a challan dated in month M+1 normally
            # settles month M's liability. Naively comparing same-calendar-
            # month labels (the first version of this query) meant a
            # completely normal, fully-paid April liability paid on time in
            # May came back as two separate HIGH-risk exceptions — a false
            # finding on routine timing, caught by testing with realistic
            # dates rather than same-month toy data. Shifting the challan
            # period back by one month aligns them for the common on-time
            # case; a challan paid materially later than one month won't
            # auto-match and will correctly still show as an exception —
            # which is the right outcome for a genuinely late payment.
            paid_rows = await conn.fetch(
                """select to_char(challan_date - interval '1 month', 'Mon-YYYY') as period, sum(amount) as total
                   from challan where engagement_id=$1 and statutory_type=$2 group by 1""",
                engagement_id, scheme,
            )
            liability = {r["period"]: float(r["total"]) for r in liability_rows}
            paid = {r["period"]: float(r["total"]) for r in paid_rows}

            if not liability and not paid:
                out.append(PayrollReconciliationRunResult(scheme=scheme, periods_analyzed=0, exceptions_found=0, total_unpaid=0.0))
                continue

            results = reconcile_payroll_statutory(scheme, liability, paid)

            run = await conn.fetchrow(
                """insert into reconciliation_run (engagement_id, recon_type, period, source_a_desc, source_b_desc, run_by,
                                                      total_records, matched_count, unmatched_count)
                   values ($1,$2,'ALL',$3,$4,$5,$6,$7,$8) returning id""",
                engagement_id, f"PAYROLL_{scheme}_RECONCILIATION", f"{scheme} Payroll Liability", f"{scheme} Challan",
                user.user_id, len(results),
                sum(1 for r in results if r.status == "Matched"),
                sum(1 for r in results if r.status != "Matched"),
            )

            exceptions_found = 0
            total_unpaid = 0.0
            for r in results:
                if r.status == "Matched":
                    continue
                exceptions_found += 1
                if r.difference > 0:
                    total_unpaid += r.difference
                risk = "HIGH" if r.difference > 0 else "MEDIUM"
                exc_row = await conn.fetchrow(
                    """insert into reconciliation_exception (run_id, period, books_amount, return_amount, difference,
                                                                reason, risk_level, suggested_action)
                       values ($1,$2,$3,$4,$5,$6,$7,$8) returning id""",
                    run["id"], r.period, r.liability, r.paid, r.difference, r.status, risk,
                    f"Confirm {scheme} challan payment for {r.period} and recompute any interest/penalty exposure",
                )
                if risk == "HIGH":
                    audit_exc = await conn.fetchrow(
                        """insert into audit_exception (engagement_id, source_type, source_id, compliance_type, period,
                                                           fs_area, difference, reason, risk_level, recommended_action, status)
                           values ($1,'RECONCILIATION',$2,$3,$4,$5,$6,$7,$8,$9,'OPEN') returning id""",
                        engagement_id, exc_row["id"], scheme, r.period, scheme, r.difference, r.status, risk,
                        f"{scheme} {r.period}: {r.status}",
                    )
                    await conn.execute(
                        "update reconciliation_exception set audit_exception_id = $1 where id = $2",
                        audit_exc["id"], exc_row["id"],
                    )

            out.append(PayrollReconciliationRunResult(
                scheme=scheme, periods_analyzed=len(results), exceptions_found=exceptions_found, total_unpaid=round(total_unpaid, 2)
            ))

    return out


class PayrollExceptionOut(BaseModel):
    scheme: str
    period: str
    liability: float | None
    paid: float | None
    reason: str
    risk_level: str


@router.get("/payroll-reconciliation", response_model=list[PayrollExceptionOut])
async def list_payroll_exceptions(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        rows = await conn.fetch(
            """select r.recon_type, e.period, e.books_amount as liability, e.return_amount as paid,
                      e.reason, e.risk_level
               from reconciliation_exception e join reconciliation_run r on r.id = e.run_id
               where r.engagement_id = $1 and r.recon_type like 'PAYROLL_%'
               order by e.risk_level""",
            engagement_id,
        )
    return [
        PayrollExceptionOut(scheme=r["recon_type"].split("_")[1], period=r["period"], liability=r["liability"],
                             paid=r["paid"], reason=r["reason"], risk_level=r["risk_level"])
        for r in rows
    ]
