"""
Auth + tenant isolation regression tests.

These protect against real bugs found in Phase 3: SET LOCAL not accepting
bind parameters, INSERT...RETURNING being filtered by the SELECT RLS
policy (broke firm creation), and passlib's broken bcrypt backend. None of
those bugs would necessarily show up as an obvious symptom in a quick
manual check — they're exactly the kind of thing a regression suite exists
to catch automatically the next time someone touches this code.
"""
from .conftest import auth_headers, unique_email


def test_signup_creates_working_account(client):
    email = unique_email("signup")
    res = client.post("/auth/signup", json={
        "firm_name": "Signup Test Firm", "admin_email": email,
        "admin_name": "Signup Test", "admin_password": "TestPass123!",
    })
    assert res.status_code == 201
    data = res.json()
    assert data["access_token"]
    assert data["firm_id"]
    assert data["user_id"]


def test_duplicate_signup_email_rejected(client):
    email = unique_email("dup")
    body = {"firm_name": "Dup Firm", "admin_email": email, "admin_name": "Dup", "admin_password": "TestPass123!"}
    first = client.post("/auth/signup", json=body)
    assert first.status_code == 201
    second = client.post("/auth/signup", json={**body, "firm_name": "Dup Firm 2"})
    assert second.status_code == 409


def test_login_wrong_password_rejected(client, firm_a):
    res = client.post("/auth/login", json={"email": firm_a["email"], "password": "WrongPassword!"})
    assert res.status_code == 401


def test_login_correct_password_succeeds(client, firm_a):
    res = client.post("/auth/login", json={"email": firm_a["email"], "password": "TestPass123!"})
    assert res.status_code == 200
    assert res.json()["access_token"]


def test_unauthenticated_request_rejected(client):
    res = client.get("/clients")
    assert res.status_code in (401, 403)


def test_firm_a_and_firm_b_cannot_see_each_others_clients(client, firm_a, firm_b):
    """The core tenant-isolation guarantee this entire system depends on."""
    a_client = client.post("/clients", headers=auth_headers(firm_a), json={
        "legal_name": "Firm A's Secret Client", "framework": "IND_AS", "listing_status": "UNLISTED",
    })
    assert a_client.status_code == 201
    a_client_id = a_client.json()["id"]

    b_list = client.get("/clients", headers=auth_headers(firm_b))
    assert b_list.status_code == 200
    assert all(c["id"] != a_client_id for c in b_list.json()), "Firm B must never see Firm A's client in a list"

    b_direct = client.get(f"/clients/{a_client_id}", headers=auth_headers(firm_b))
    assert b_direct.status_code == 404, "Cross-tenant direct access must 404, not leak data or even confirm existence via 403"


def test_role_based_write_permission_enforced(client, firm_a):
    """An ARTICLE-role user must be blocked from write operations, even
    though the underlying JWT is otherwise valid."""
    from app.security import issue_jwt

    article_token = issue_jwt(firm_a["user_id"], firm_a["firm_id"], "ARTICLE")
    res = client.post(
        "/clients", headers={"Authorization": f"Bearer {article_token}"},
        json={"legal_name": "Should Be Blocked", "framework": "IND_AS", "listing_status": "UNLISTED"},
    )
    assert res.status_code == 403
