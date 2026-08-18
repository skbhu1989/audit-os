"""
Test configuration. Sets the test database DSN BEFORE importing the app
(app.db reads DATABASE_DSN at module import time), so every test in this
suite runs against `audit_os_test`, never the real `audit_os` database.

Each test creates its own uniquely-named firm/user (random suffix) rather
than relying on transaction rollback — simpler, and it also means tests
exercise the exact same signup/login code path real users go through,
rather than a fixture that pokes data directly into the DB.
"""
import os
import uuid

os.environ.setdefault("DATABASE_DSN", "postgresql://app_runtime:runtime_dev_pw@127.0.0.1:5432/audit_os_test")
os.environ.setdefault("JWT_SECRET", "test-suite-secret")
os.environ.setdefault("ENVIRONMENT", "test")  # disables the rate limiter — see app/rate_limit.py's own comment on why

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@test.example.com"


@pytest.fixture()
def firm_a(client):
    """A fully signed-up firm with a FIRM_ADMIN user, ready to use."""
    email = unique_email("firma")
    res = client.post("/auth/signup", json={
        "firm_name": f"Test Firm A {uuid.uuid4().hex[:6]}",
        "admin_email": email, "admin_name": "Test Admin A", "admin_password": "TestPass123!",
    })
    assert res.status_code == 201, res.text
    data = res.json()
    return {"token": data["access_token"], "firm_id": data["firm_id"], "user_id": data["user_id"], "email": email}


@pytest.fixture()
def firm_b(client):
    """A second, independent firm — used for every tenant-isolation test."""
    email = unique_email("firmb")
    res = client.post("/auth/signup", json={
        "firm_name": f"Test Firm B {uuid.uuid4().hex[:6]}",
        "admin_email": email, "admin_name": "Test Admin B", "admin_password": "TestPass123!",
    })
    assert res.status_code == 201, res.text
    data = res.json()
    return {"token": data["access_token"], "firm_id": data["firm_id"], "user_id": data["user_id"], "email": email}


def auth_headers(firm: dict) -> dict:
    return {"Authorization": f"Bearer {firm['token']}"}


@pytest.fixture()
def engagement_a(client, firm_a):
    """A real client + engagement under firm_a, created through the real API."""
    c = client.post("/clients", headers=auth_headers(firm_a), json={
        "legal_name": f"Test Client {uuid.uuid4().hex[:6]}", "framework": "IND_AS", "listing_status": "UNLISTED",
    })
    assert c.status_code == 201, c.text
    client_id = c.json()["id"]

    e = client.post("/engagements", headers=auth_headers(firm_a), json={
        "client_id": client_id, "financial_year": "2025-26", "reporting_date": "2026-03-31", "framework": "IND_AS",
    })
    assert e.status_code == 201, e.text
    return {"client_id": client_id, "engagement_id": e.json()["id"], **firm_a}
