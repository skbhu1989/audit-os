"""
Auto-drafts working paper content (objective, population, sample, testing
result, conclusion) from reconciliation runs and JE risk-scoring results.

Deliberately template-based, not LLM-generated: per Section B's separation of
concerns, the numbers and structure here are deterministic and reproducible.
An LLM layer can later polish the prose or answer follow-up questions about a
working paper, but the objective/assertion/standard/population/conclusion
fields themselves come from what actually happened in the reconciliation run
— not from a model's best guess at what a working paper should say.

Every draft is explicit that it is a DRAFT requiring reviewer sign-off
(Section 50/CL: AI drafts, humans conclude) — the conclusion text never
asserts a final audit opinion.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class WpDraft:
    wp_code: str
    objective: str
    fs_assertion: list[str]
    applicable_standard: list[str]
    fs_area: str
    population_desc: str
    sample: dict
    testing_result: dict
    conclusion: str


def draft_gst_reconciliation_wp(recon_type: str, run_summary: dict, exceptions: list[dict]) -> WpDraft:
    total = run_summary.get("total_records", 0)
    matched = run_summary.get("matched_count", 0)
    unmatched = run_summary.get("unmatched_count", 0)
    partial = run_summary.get("partial_count", 0)

    label = {
        "GST_BOOKS_VS_GSTR1": ("Books vs GSTR-1", "revenue completeness and accuracy of GST reporting"),
        "GST_PURCHASE_VS_GSTR2B": ("Purchase Register vs GSTR-2B", "input tax credit availability and accuracy"),
        "GST_GSTR1_VS_GSTR3B": ("GSTR-1 vs GSTR-3B", "consistency of turnover reported across GST returns"),
    }.get(recon_type, (recon_type, "GST reconciliation"))
    title, purpose = label

    material_count = sum(1 for e in exceptions if e.get("risk_level") in ("HIGH", "CRITICAL"))

    if unmatched == 0 and partial == 0:
        conclusion = (
            f"All {total} records reconciled between {title} with no unmatched or partially "
            f"matched items identified. Based on procedures performed, no exceptions were noted "
            f"requiring further audit attention on this reconciliation. DRAFT — pending reviewer sign-off."
        )
    else:
        conclusion = (
            f"Of {total} records reconciled between {title}, {matched} matched, {partial} were "
            f"partially matched (amount differences), and {unmatched} were unmatched. "
            f"{material_count} exception(s) exceed the risk threshold for further investigation "
            f"(see linked exceptions). Auditor should obtain client explanation and supporting "
            f"documentation before concluding on this area. DRAFT — pending reviewer sign-off, "
            f"NOT a final conclusion."
        )

    return WpDraft(
        wp_code=f"WP-{recon_type}",
        objective=f"Reconcile {title} to assess {purpose}, and identify exceptions requiring audit follow-up.",
        fs_assertion=["COMPLETENESS", "ACCURACY"],
        applicable_standard=["CGST Act & Rules", "SA 500", "SA 330"],
        fs_area="GST",
        population_desc=f"{total} records ({title})",
        sample={"method": "100% (system reconciliation)", "size": total},
        testing_result={"matched": matched, "partially_matched": partial, "unmatched": unmatched},
        conclusion=conclusion,
    )


def draft_tds_reconciliation_wp(run_summary: dict, exceptions: list[dict]) -> WpDraft:
    total = run_summary.get("total_records", 0)
    matched = run_summary.get("matched_count", 0)
    unmatched = run_summary.get("unmatched_count", 0)
    total_interest = sum(e.get("interest_exposure", 0) or 0 for e in exceptions)

    if unmatched == 0:
        conclusion = (
            f"All {total} TDS section(s) tested reconcile between the deduction ledger, challan "
            f"payments, and filed return with no exceptions identified. DRAFT — pending reviewer sign-off."
        )
    else:
        conclusion = (
            f"Of {total} TDS section(s) tested, {matched} matched and {unmatched} showed a "
            f"deduction/payment/return discrepancy. Estimated aggregate interest exposure under "
            f"Sec 201(1A): ₹{total_interest:,.2f} (simplified calculation — see working paper detail "
            f"for section-wise basis). Auditor should confirm subsequent payment or revised filing "
            f"before concluding on disallowance/provision adequacy. DRAFT — pending reviewer sign-off, "
            f"NOT a final conclusion."
        )

    return WpDraft(
        wp_code="WP-TDS-RECONCILIATION",
        objective="Reconcile TDS deducted (ledger) against TDS paid (challan) and TDS reported (return) "
                   "by section, and quantify interest exposure on any shortfall.",
        fs_assertion=["COMPLETENESS", "ACCURACY"],
        applicable_standard=["Income Tax Act 1961 — Chapter XVII-B", "SA 250"],
        fs_area="TDS",
        population_desc=f"{total} TDS sections with activity in the period",
        sample={"method": "100% (system reconciliation)", "size": total},
        testing_result={"matched": matched, "unmatched": unmatched},
        conclusion=conclusion,
    )


def draft_journal_testing_wp(risk_distribution: dict, top_journals: list[dict], materiality: float | None) -> WpDraft:
    total = sum(risk_distribution.values())
    high_critical = risk_distribution.get("HIGH", 0) + risk_distribution.get("CRITICAL", 0)

    if high_critical == 0:
        conclusion = (
            f"100% of the journal population ({total} entries) was risk-scored. No entries scored "
            f"HIGH or CRITICAL risk. Based on procedures performed, no indicators of management "
            f"override or unusual manual adjustment were identified requiring further investigation. "
            f"DRAFT — pending reviewer sign-off."
        )
    else:
        top_desc = "; ".join(
            f"{j['id']} (₹{j['amount']:,.0f}, {j['risk_level']}: {', '.join(j['risk_reasons'] or [])})"
            for j in top_journals[:5]
        )
        conclusion = (
            f"100% of the journal population ({total} entries) was risk-scored. {high_critical} "
            f"entries scored HIGH or CRITICAL, indicating elevated risk of management override, "
            f"unusual timing, or reversal patterns requiring further investigation. Highest-risk "
            f"entries: {top_desc}. Auditor should obtain business rationale and supporting "
            f"documentation for each HIGH/CRITICAL entry, with particular attention to any above "
            f"performance materiality"
            + (f" (₹{materiality:,.0f})" if materiality else "")
            + ". DRAFT — pending reviewer sign-off, NOT a final conclusion."
        )

    return WpDraft(
        wp_code="WP-JOURNAL-TESTING",
        objective="Test 100% of the journal entry population for indicators of management override, "
                   "unusual timing, round-number amounts, and reversal patterns (SA 240).",
        fs_assertion=["EXISTENCE", "CLASSIFICATION", "COMPLETENESS"],  # schema's fs_assertion enum
        # (Section 41) has no OCCURRENCE value, though journal testing is
        # traditionally framed around occurrence for P&L transactions;
        # EXISTENCE is the nearest available assertion, not a perfect
        # substitute — flagged rather than silently treated as equivalent.
        applicable_standard=["SA 240", "SA 330"],
        fs_area="General Ledger",
        population_desc=f"{total} journal entries (100% of population)",
        sample={"method": "100% (system risk-scoring)", "size": total},
        testing_result=risk_distribution,
        conclusion=conclusion,
    )
