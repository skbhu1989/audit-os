"""
Database access layer.

Every request that needs tenant-scoped data goes through `tenant_conn()`,
which opens a transaction and issues `SET LOCAL app.current_firm_id`
before any query runs. Postgres row-level security (migrations 010/011)
then enforces isolation at the database layer — even if application code
has a bug, a query simply cannot return another firm's rows.

The pool connects as `app_runtime`, a non-owner role, because RLS is
bypassed for table owners and superusers. Auth/bootstrap operations that
must run *before* a firm_id is known (signup, login) use `system_conn()`,
which opens a transaction with no tenant context set — by RLS design this
means those queries can only touch tables without RLS or explicitly
firm-scoped WHERE clauses written by hand (see routers/auth.py).
"""
import os
import asyncpg
from contextlib import asynccontextmanager

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

DATABASE_DSN = os.environ.get("DATABASE_DSN")
if not DATABASE_DSN:
    if ENVIRONMENT == "production":
        raise RuntimeError(
            "DATABASE_DSN must be set via environment variable when ENVIRONMENT=production. "
            "Refusing to start with the development fallback connection string."
        )
    DATABASE_DSN = "postgresql://app_runtime:runtime_dev_pw@127.0.0.1:5432/audit_os"

_pool: asyncpg.Pool | None = None


async def init_pool():
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_DSN, min_size=1, max_size=10)


async def close_pool():
    if _pool:
        await _pool.close()


@asynccontextmanager
async def tenant_conn(firm_id: str):
    """Yields a connection inside a transaction with tenant context set."""
    async with _pool.acquire() as conn:
        async with conn.transaction():
            # SET LOCAL is a utility statement and does not accept $-placeholders;
            # set_config() is the parameterized equivalent (true = local to transaction).
            await conn.execute("SELECT set_config('app.current_firm_id', $1, true)", firm_id)
            yield conn


@asynccontextmanager
async def system_conn():
    """Yields a connection with NO tenant context — for signup/login only."""
    async with _pool.acquire() as conn:
        async with conn.transaction():
            yield conn
