from uuid import UUID
import json
import re
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db import tenant_conn
from ..deps import get_current_user, require_roles, CurrentUser
from ..working_papers import draft_gst_reconciliation_wp, draft_tds_reconciliation_wp, draft_journal_testing_wp

router = APIRouter(prefix="/engagements/{engagement_id}/working-papers", tags=["working-papers"])
WRITE_ROLES = ("FIRM_ADMIN", "PARTNER", "MANAGER", "SENIOR", "ARTICLE")
REVIEW_ROLES = ("FIRM_ADMIN", "PARTNER", "MANAGER", "EQCR_REVIEWER")
APPROVE_ROLES = ("FIRM_ADMIN", "PARTNER")


async def _upsert_wp(conn, engagement_id, draft, source_run_id=None):
    """A working paper is versioned (Section 41/BJ); re-running auto-draft
    for the same wp_code creates a new version rather than silently
    overwriting a draft someone may already be reviewing."""
    existing = await conn.fetchrow(
        "select id, version from working_paper where engagement_id=$1 and wp_code=$2 order by version desc limit 1",
        engagement_id, draft.wp_code,
    )
    version = (existing["version"] + 1) if existing else 1
    supersedes = existing["id"] if existing else None

    row = await conn.fetchrow(
        """insert into working_paper (engagement_id, wp_code, objective, fs_assertion, applicable_standard,
                                        population_desc, sample, testing_result, conclusion, status, version,
                                        supersedes_wp_id)
           values ($1,$2,$3,$4,$5,$6,$7,$8,$9,'DRAFT',$10,$11) returning id""",
        engagement_id, draft.wp_code, draft.objective, draft.fs_assertion, draft.applicable_standard,
        draft.population_desc, json.dumps(draft.sample), json.dumps(draft.testing_result),
        draft.conclusion, version, supersedes,
    )
    return row["id"]


class WpDraftOut(BaseModel):
    id: UUID
    wp_code: str
    version: int
    status: str


@router.post("/auto-draft/gst", response_model=list[WpDraftOut])
async def auto_draft_gst_wps(engagement_id: UUID, user: CurrentUser = Depends(require_roles(*WRITE_ROLES))):
    async with tenant_conn(user.firm_id) as conn:
        runs = await conn.fetch(
            "select id, recon_type, total_records, matched_count, partial_count, unmatched_count "
            "from reconciliation_run where engagement_id=$1 and recon_type like 'GST_%' order by run_at desc",
            engagement_id,
        )
        # only the latest run per recon_type
        seen_types = set()
        out = []
        for run in runs:
            if run["recon_type"] in seen_types:
                continue
            seen_types.add(run["recon_type"])
            exceptions = await conn.fetch(
                "select risk_level from reconciliation_exception where run_id=$1", run["id"]
            )
            draft = draft_gst_reconciliation_wp(run["recon_type"], dict(run), [dict(e) for e in exceptions])
            wp_id = await _upsert_wp(conn, engagement_id, draft, run["id"])
            row = await conn.fetchrow("select id, wp_code, version, status from working_paper where id=$1", wp_id)
            out.append(WpDraftOut(**dict(row)))
    return out


@router.post("/auto-draft/tds", response_model=WpDraftOut)
async def auto_draft_tds_wp(engagement_id: UUID, user: CurrentUser = Depends(require_roles(*WRITE_ROLES))):
    async with tenant_conn(user.firm_id) as conn:
        run = await conn.fetchrow(
            "select id, total_records, matched_count, unmatched_count from reconciliation_run "
            "where engagement_id=$1 and recon_type='TDS_RECONCILIATION' order by run_at desc limit 1",
            engagement_id,
        )
        if not run:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No TDS reconciliation run found — run it first")
        exceptions = await conn.fetch(
            """select reason from reconciliation_exception where run_id=$1""", run["id"]
        )
        # interest exposure was embedded in the reason text by the reconciliation
        # router rather than a dedicated column (Phase 6's schema-fit tradeoff,
        # documented in that phase's README) — reparse it here rather than
        # duplicating the number, so the WP and the exception list can't drift.
        exc_dicts = []
        for e in exceptions:
            m = re.search(r"interest exposure ([\d,]+\.\d+)", e["reason"])
            exc_dicts.append({"interest_exposure": float(m.group(1).replace(",", "")) if m else 0.0})

        draft = draft_tds_reconciliation_wp(dict(run), exc_dicts)
        wp_id = await _upsert_wp(conn, engagement_id, draft, run["id"])
        row = await conn.fetchrow("select id, wp_code, version, status from working_paper where id=$1", wp_id)
    return WpDraftOut(**dict(row))


@router.post("/auto-draft/journal-testing", response_model=WpDraftOut)
async def auto_draft_journal_testing_wp(engagement_id: UUID, user: CurrentUser = Depends(require_roles(*WRITE_ROLES))):
    async with tenant_conn(user.firm_id) as conn:
        eng = await conn.fetchrow("select performance_materiality from engagement where id=$1", engagement_id)
        if not eng:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Engagement not found")
        risk_rows = await conn.fetch(
            "select risk_level, count(*) from journal where engagement_id=$1 and risk_level is not null group by risk_level",
            engagement_id,
        )
        if not risk_rows:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No journal risk scores found — run journal-risk analysis first")
        distribution = {"LOW": 0, "MODERATE": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        for r in risk_rows:
            distribution[r["risk_level"]] = r["count"]

        top_journals = await conn.fetch(
            """select id, amount, risk_level, risk_reasons from journal
               where engagement_id=$1 and risk_score is not null order by risk_score desc limit 5""",
            engagement_id,
        )
        materiality = float(eng["performance_materiality"]) if eng["performance_materiality"] else None
        draft = draft_journal_testing_wp(distribution, [
            {"id": str(j["id"])[:8], "amount": float(j["amount"]), "risk_level": j["risk_level"], "risk_reasons": j["risk_reasons"]}
            for j in top_journals
        ], materiality)
        wp_id = await _upsert_wp(conn, engagement_id, draft)
        row = await conn.fetchrow("select id, wp_code, version, status from working_paper where id=$1", wp_id)
    return WpDraftOut(**dict(row))


class WorkingPaperOut(BaseModel):
    id: UUID
    wp_code: str
    objective: str
    fs_assertion: list[str]
    applicable_standard: list[str] | None
    population_desc: str | None
    conclusion: str | None
    status: str
    version: int
    preparer_id: UUID | None
    reviewer_id: UUID | None
    approver_id: UUID | None


@router.get("", response_model=list[WorkingPaperOut])
async def list_working_papers(engagement_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        rows = await conn.fetch(
            """select id, wp_code, objective, fs_assertion, applicable_standard, population_desc,
                      conclusion, status, version, preparer_id, reviewer_id, approver_id
               from working_paper where engagement_id=$1 order by wp_code, version desc""",
            engagement_id,
        )
    return [WorkingPaperOut(**dict(r)) for r in rows]


@router.get("/{wp_id}", response_model=WorkingPaperOut)
async def get_working_paper(engagement_id: UUID, wp_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        row = await conn.fetchrow(
            """select id, wp_code, objective, fs_assertion, applicable_standard, population_desc,
                      conclusion, status, version, preparer_id, reviewer_id, approver_id
               from working_paper where id=$1 and engagement_id=$2""",
            wp_id, engagement_id,
        )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Working paper not found")
    return WorkingPaperOut(**dict(row))


# ---------- Sign-off state machine ----------
# DRAFT -> (prepare) -> PREPARED -> (review) -> REVIEWED -> (approve) -> APPROVED
# Segregation of duties (SA 220 quality control principle): the same person
# cannot prepare and then review or approve their own working paper.

async def _get_wp_for_transition(conn, engagement_id, wp_id):
    row = await conn.fetchrow(
        "select id, status, preparer_id, reviewer_id from working_paper where id=$1 and engagement_id=$2",
        wp_id, engagement_id,
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Working paper not found")
    return row


@router.post("/{wp_id}/prepare", status_code=204)
async def prepare_working_paper(
    engagement_id: UUID, wp_id: UUID, user: CurrentUser = Depends(require_roles(*WRITE_ROLES))
):
    async with tenant_conn(user.firm_id) as conn:
        wp = await _get_wp_for_transition(conn, engagement_id, wp_id)
        if wp["status"] != "DRAFT":
            raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot prepare a working paper in status {wp['status']} (must be DRAFT)")
        await conn.execute(
            "update working_paper set status='PREPARED', preparer_id=$1, prepared_at=now() where id=$2",
            user.user_id, wp_id,
        )


@router.post("/{wp_id}/review", status_code=204)
async def review_working_paper(
    engagement_id: UUID, wp_id: UUID, user: CurrentUser = Depends(require_roles(*REVIEW_ROLES))
):
    async with tenant_conn(user.firm_id) as conn:
        wp = await _get_wp_for_transition(conn, engagement_id, wp_id)
        if wp["status"] != "PREPARED":
            raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot review a working paper in status {wp['status']} (must be PREPARED)")
        if wp["preparer_id"] and str(wp["preparer_id"]) == user.user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Segregation of duties: the preparer cannot also review this working paper (SA 220)")
        await conn.execute(
            "update working_paper set status='REVIEWED', reviewer_id=$1, reviewed_at=now() where id=$2",
            user.user_id, wp_id,
        )


class ApproveRequest(BaseModel):
    final_conclusion: str | None = None  # allows the approver to refine the auto-drafted conclusion


@router.post("/{wp_id}/approve", status_code=204)
async def approve_working_paper(
    engagement_id: UUID, wp_id: UUID, body: ApproveRequest,
    user: CurrentUser = Depends(require_roles(*APPROVE_ROLES)),
):
    async with tenant_conn(user.firm_id) as conn:
        wp = await _get_wp_for_transition(conn, engagement_id, wp_id)
        if wp["status"] != "REVIEWED":
            raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot approve a working paper in status {wp['status']} (must be REVIEWED)")
        if wp["preparer_id"] and str(wp["preparer_id"]) == user.user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Segregation of duties: the preparer cannot also approve this working paper (SA 220)")
        if body.final_conclusion:
            await conn.execute("update working_paper set conclusion=$1 where id=$2", body.final_conclusion, wp_id)
        await conn.execute(
            "update working_paper set status='APPROVED', approver_id=$1, approved_at=now() where id=$2",
            user.user_id, wp_id,
        )


# ---------- Evidence linking ----------

class LinkEvidenceRequest(BaseModel):
    document_id: UUID
    description: str | None = None


@router.post("/{wp_id}/evidence", status_code=204)
async def link_evidence(
    engagement_id: UUID, wp_id: UUID, body: LinkEvidenceRequest,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    async with tenant_conn(user.firm_id) as conn:
        wp = await conn.fetchrow(
            "select id, procedure_id, fs_assertion from working_paper where id=$1 and engagement_id=$2", wp_id, engagement_id
        )
        if not wp:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Working paper not found")
        doc = await conn.fetchrow("select id from document where id=$1 and engagement_id=$2", body.document_id, engagement_id)
        if not doc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

        procedure_id = wp["procedure_id"]
        if not procedure_id:
            # audit_evidence.procedure_id is NOT NULL by schema design (evidence
            # is evidence FOR a procedure) — an auto-drafted WP doesn't have one
            # yet, so create a minimal procedure row on first evidence link
            # rather than loosening the constraint. audit_procedure.assertions
            # is itself NOT NULL, so it's seeded from the WP's own fs_assertion
            # rather than an arbitrary placeholder — they're testing the same
            # assertions by construction.
            proc = await conn.fetchrow(
                "insert into audit_procedure (engagement_id, title, assertions) values ($1,$2,$3) returning id",
                engagement_id, f"Procedure for {wp_id}", wp["fs_assertion"],
            )
            procedure_id = proc["id"]
            await conn.execute("update working_paper set procedure_id=$1 where id=$2", procedure_id, wp_id)

        evidence = await conn.fetchrow(
            """insert into audit_evidence (procedure_id, document_id, description, obtained, obtained_at)
               values ($1,$2,$3,true,now()) returning id""",
            procedure_id, body.document_id, body.description,
        )
        await conn.execute(
            "insert into working_paper_evidence (working_paper_id, evidence_id) values ($1,$2) on conflict do nothing",
            wp_id, evidence["id"],
        )


class EvidenceOut(BaseModel):
    document_id: UUID
    file_name: str
    category: str
    description: str | None


@router.get("/{wp_id}/evidence", response_model=list[EvidenceOut])
async def list_evidence(engagement_id: UUID, wp_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with tenant_conn(user.firm_id) as conn:
        rows = await conn.fetch(
            """select d.id as document_id, d.file_name, d.category, ae.description
               from working_paper_evidence wpe
               join audit_evidence ae on ae.id = wpe.evidence_id
               join document d on d.id = ae.document_id
               where wpe.working_paper_id = $1""",
            wp_id,
        )
    return [EvidenceOut(**dict(r)) for r in rows]
