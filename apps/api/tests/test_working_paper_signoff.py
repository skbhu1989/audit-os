"""
Working paper sign-off regression tests (Phase 9).

No "invite a team member" API endpoint exists anywhere in this system —
every manual test session in this build's history created additional
users (MANAGER, second PARTNER) via a direct DB insert plus a directly-
minted JWT, and this suite follows the same pattern rather than pretending
an endpoint exists that doesn't. That absence is itself a real, honest gap
worth flagging: there is no way for a firm to add a team member through
the actual product today.
"""
import os
import io
import uuid
import asyncpg
import pytest
from app.security import issue_jwt
from .conftest import auth_headers

DSN = os.environ.get("DATABASE_DSN", "postgresql://app_runtime:runtime_dev_pw@127.0.0.1:5432/audit_os_test")

SAMPLE_GL = """Voucher No,Date,User,Narration,Debit Account,Credit Account,Amount
JE-001,05/04/2025,Test User,Test entry for sign-off regression test,Cash & Bank Balances,Revenue from Operations,50000
"""


async def _create_team_member(firm_id: str, role: str) -> dict:
    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute("select set_config('app.current_firm_id', $1, false)", firm_id)
        user_id = str(uuid.uuid4())
        email = f"{role.lower()}-{uuid.uuid4().hex[:6]}@test-suite.example"
        await conn.execute(
            "insert into app_user (id, firm_id, email, full_name, role) values ($1,$2,$3,$4,$5)",
            user_id, firm_id, email, f"Test {role}", role,
        )
    finally:
        await conn.close()
    token = issue_jwt(user_id, firm_id, role)
    return {"user_id": user_id, "token": token}


@pytest.mark.asyncio
async def test_journal_testing_wp_signoff_enforces_segregation_of_duties(client, engagement_a):
    headers = auth_headers(engagement_a)
    eng_id = engagement_a["engagement_id"]
    firm_id = engagement_a["firm_id"]

    # A journal must exist for journal-risk scoring to produce any scored
    # rows — running the scorer on zero journals succeeds (200) but produces
    # nothing for the auto-draft endpoint to work with (it correctly 404s
    # in that case). Upload one real entry first.
    upload = client.post(
        f"/engagements/{eng_id}/data/upload", headers=headers,
        data={"dataset_type": "GENERAL_LEDGER", "on_duplicate": "ASK"},
        files={"file": ("gl.csv", io.BytesIO(SAMPLE_GL.encode()), "text/csv")},
    )
    assert upload.status_code == 201, upload.text

    risk_run = client.post(f"/engagements/{eng_id}/analytics/journal-risk/run", headers=headers)
    assert risk_run.status_code == 200, risk_run.text

    draft = client.post(f"/engagements/{eng_id}/working-papers/auto-draft/journal-testing", headers=headers)
    assert draft.status_code == 200, draft.text
    wp_id = draft.json()["id"]

    # Preparer (the firm_admin who created the engagement) prepares it.
    prep = client.post(f"/engagements/{eng_id}/working-papers/{wp_id}/prepare", headers=headers)
    assert prep.status_code == 204, prep.text

    # The SAME user attempting to review their own work must be blocked.
    same_user_review = client.post(f"/engagements/{eng_id}/working-papers/{wp_id}/review", headers=headers)
    assert same_user_review.status_code == 403, "Preparer must not be able to review their own working paper"

    # A genuinely different MANAGER can review.
    manager = await _create_team_member(firm_id, "MANAGER")
    manager_headers = {"Authorization": f"Bearer {manager['token']}"}
    review = client.post(f"/engagements/{eng_id}/working-papers/{wp_id}/review", headers=manager_headers)
    assert review.status_code == 204, review.text

    # The preparer attempting to approve their own (now-reviewed) work must
    # also be blocked, even though a different user reviewed it in between.
    same_user_approve = client.post(
        f"/engagements/{eng_id}/working-papers/{wp_id}/approve", headers=headers, json={}
    )
    assert same_user_approve.status_code == 403, "Preparer must not be able to approve their own working paper"

    # A genuinely different PARTNER can approve, with a real final conclusion.
    partner = await _create_team_member(firm_id, "PARTNER")
    partner_headers = {"Authorization": f"Bearer {partner['token']}"}
    approve = client.post(
        f"/engagements/{eng_id}/working-papers/{wp_id}/approve", headers=partner_headers,
        json={"final_conclusion": "Reviewed and approved for regression test purposes."},
    )
    assert approve.status_code == 204, approve.text

    final = client.get(f"/engagements/{eng_id}/working-papers", headers=headers)
    wp = next(w for w in final.json() if w["id"] == wp_id)
    assert wp["status"] == "APPROVED"
    assert str(wp["preparer_id"]) != str(wp["reviewer_id"])
    assert str(wp["reviewer_id"]) != str(wp["approver_id"])
    assert str(wp["preparer_id"]) != str(wp["approver_id"])
