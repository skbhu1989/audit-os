"""
Database-level security regression tests.

These test the database directly via asyncpg (not through the API) because
the bugs they protect against are database-layer bugs — RLS policies and
triggers — that could theoretically still be broken even if every API
endpoint continues to work (an API test wouldn't necessarily catch a
missing RLS policy on a table no endpoint happens to query with a bad
WHERE clause). This is deliberately a second, independent layer of
protection under the API-level tests, not a duplicate of them.
"""
import os
import uuid
import pytest
import pytest_asyncio
import asyncpg

DSN = os.environ.get("DATABASE_DSN", "postgresql://app_runtime:runtime_dev_pw@127.0.0.1:5432/audit_os_test")


@pytest_asyncio.fixture()
async def db_conn():
    conn = await asyncpg.connect(DSN)
    yield conn
    await conn.close()


async def _set_context(conn, firm_id: str):
    await conn.execute("select set_config('app.current_firm_id', $1, false)", firm_id)


async def _clear_context(conn):
    """Session-level set_config persists across statements on the same
    connection — _seed_two_firms leaves context on whichever firm was
    created last, so any test needing a genuinely clean slate (or a
    specific firm's context) must set it explicitly rather than assume
    one. Caught by running the tests, not by reading the fixture code."""
    await conn.execute("select set_config('app.current_firm_id', '', false)")


async def _seed_two_firms(conn):
    """Creates two isolated firms/clients/engagements directly, bypassing
    RLS by using set_config with each firm's own id at insert time (the
    same pattern the real API uses). Leaves the connection's session
    context on firm B's id (whichever was created last) — callers must
    explicitly (re)set context before their own operations, not assume
    a particular firm is active."""
    ids = {}
    for label in ("a", "b"):
        firm_id = str(uuid.uuid4())
        await _set_context(conn, firm_id)
        await conn.execute("insert into firm (id, name) values ($1, $2)", firm_id, f"RLS Test Firm {label}")
        client_id = str(uuid.uuid4())
        await conn.execute(
            "insert into client (id, firm_id, legal_name, framework) values ($1,$2,$3,'IND_AS')",
            client_id, firm_id, f"RLS Test Client {label}",
        )
        eng_id = str(uuid.uuid4())
        await conn.execute(
            "insert into engagement (id, client_id, financial_year, reporting_date, framework) values ($1,$2,'2025-26','2026-03-31','IND_AS')",
            eng_id, client_id,
        )
        ids[label] = {"firm_id": firm_id, "client_id": client_id, "engagement_id": eng_id}
    return ids


@pytest.mark.asyncio
async def test_journal_line_rls_isolates_tenants(db_conn):
    """Regression test for the CTO audit finding: journal_line had NO RLS
    at all until migration 029. This directly proves isolation now works."""
    ids = await _seed_two_firms(db_conn)
    await _set_context(db_conn, ids["a"]["firm_id"])

    journal_id = str(uuid.uuid4())
    account_id = str(uuid.uuid4())
    await db_conn.execute("insert into account (id, engagement_id, ledger_name) values ($1,$2,'Test Ledger')", account_id, ids["a"]["engagement_id"])
    await db_conn.execute(
        "insert into journal (id, engagement_id, posted_date, amount) values ($1,$2,current_date,1000)",
        journal_id, ids["a"]["engagement_id"],
    )
    await db_conn.execute(
        "insert into journal_line (journal_id, account_id, debit, credit) values ($1,$2,1000,0)",
        journal_id, account_id,
    )

    await _set_context(db_conn, ids["b"]["firm_id"])
    visible_to_b = await db_conn.fetchval("select count(*) from journal_line where journal_id=$1", journal_id)
    assert visible_to_b == 0, "Firm B must see zero rows of Firm A's journal_line data"

    await _set_context(db_conn, ids["a"]["firm_id"])
    visible_to_a = await db_conn.fetchval("select count(*) from journal_line where journal_id=$1", journal_id)
    assert visible_to_a == 1, "Firm A must see its own journal_line data"


@pytest.mark.asyncio
async def test_audit_trail_event_rls_isolates_tenants(db_conn):
    """Regression test for the most serious CTO audit finding: the audit
    log itself had no tenant isolation until migration 029."""
    ids = await _seed_two_firms(db_conn)
    await _set_context(db_conn, ids["a"]["firm_id"])

    # The journal insert below fires the real audit trigger, generating a
    # real audit_trail_event row scoped to firm A.
    account_id = str(uuid.uuid4())
    await db_conn.execute("insert into account (id, engagement_id, ledger_name) values ($1,$2,'Test Ledger 2')", account_id, ids["a"]["engagement_id"])
    await db_conn.execute(
        "insert into journal (engagement_id, posted_date, amount) values ($1,current_date,500)",
        ids["a"]["engagement_id"],
    )

    await _set_context(db_conn, ids["b"]["firm_id"])
    b_sees = await db_conn.fetchval(
        "select count(*) from audit_trail_event where engagement_id=$1", ids["a"]["engagement_id"]
    )
    assert b_sees == 0, "Firm B must never see Firm A's audit trail events"

    await _set_context(db_conn, ids["a"]["firm_id"])
    a_sees = await db_conn.fetchval(
        "select count(*) from audit_trail_event where engagement_id=$1", ids["a"]["engagement_id"]
    )
    assert a_sees > 0, "Firm A must see its own audit trail events"


@pytest.mark.asyncio
async def test_no_tenant_context_sees_nothing():
    """Fails closed: a connection that has NEVER called set_config for
    app.current_firm_id (matching a real request with no tenant context
    set) must see zero rows from every tenant-scoped table.

    Deliberately uses its own fresh connection rather than db_conn/
    _clear_context — setting the GUC to '' and casting ::uuid raises
    'invalid input syntax for type uuid' (empty string isn't NULL), which
    is a different, incorrect test of a state no real request produces.
    A connection that never touched the setting at all is the honest
    equivalent of 'no context.'"""
    seed_conn = await asyncpg.connect(DSN)
    await _seed_two_firms(seed_conn)
    await seed_conn.close()

    fresh_conn = await asyncpg.connect(DSN)
    try:
        count = await fresh_conn.fetchval("select count(*) from client")
        assert count == 0, "With no tenant context ever set on this connection, zero rows should be visible"
    finally:
        await fresh_conn.close()


@pytest.mark.asyncio
async def test_client_gstin_write_path_does_not_crash(db_conn):
    """Regression test for a real bug found by systematic audit, not by
    feature testing: client_gstin's audit trigger assumed an engagement_id
    column that doesn't exist on this table, and had never been exercised
    by any feature test because no endpoint writes to it. This proves the
    fix (migration 028) actually works, by exercising the exact path that
    was silently broken."""
    ids = await _seed_two_firms(db_conn)
    await _set_context(db_conn, ids["a"]["firm_id"])
    # Should not raise — this exact statement crashed before migration 028.
    await db_conn.execute(
        "insert into client_gstin (client_id, gstin, state) values ($1, '27AAACT1234A1Z5', 'Maharashtra')",
        ids["a"]["client_id"],
    )
    await db_conn.execute("update client_gstin set state='MH' where client_id=$1", ids["a"]["client_id"])
    await db_conn.execute("delete from client_gstin where client_id=$1", ids["a"]["client_id"])
