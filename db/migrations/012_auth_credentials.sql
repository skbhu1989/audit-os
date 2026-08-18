-- ============================================================
-- 012_auth_credentials.sql
-- Password hashes live in a separate table from app_user, so that
-- the (much more frequently selected/joined) app_user table never
-- carries sensitive credential material, and access to it can be
-- audited/restricted independently.
-- ============================================================

alter table app_user add column mfa_secret text;   -- set on enroll, used once mfa_enabled = true

create table app_user_credential (
  user_id        uuid primary key references app_user(id) on delete cascade,
  password_hash  text not null,
  updated_at     timestamptz not null default now()
);

alter table app_user_credential enable row level security;
create policy app_user_credential_isolation on app_user_credential
  using (exists (
    select 1 from app_user u where u.id = app_user_credential.user_id
      and u.firm_id = current_setting('app.current_firm_id', true)::uuid
  ));

-- ---------- Pre-auth lookup ----------
-- Login cannot know app.current_firm_id in advance — that's precisely what
-- authenticating determines — so the normal RLS-scoped SELECT policies above
-- would block the lookup entirely (return zero rows, not an error, which is
-- the correct fail-closed behaviour for every OTHER access path but wrong
-- here). The fix is not to relax the RLS policy or query with elevated
-- privileges from the API; it's a single narrow SECURITY DEFINER function,
-- owned by the migration role (which owns the tables and so bypasses RLS),
-- that exposes exactly the columns login needs and nothing else. EXECUTE is
-- revoked from PUBLIC and granted only to the API's runtime role, so it
-- cannot be invoked as a generic cross-tenant query surface.
create function fn_authenticate_lookup(p_email citext)
returns table (
  user_id uuid, firm_id uuid, role user_role, is_active boolean,
  mfa_enabled boolean, mfa_secret text, password_hash text
)
security definer
set search_path = public
language sql
as $$
  select u.id, u.firm_id, u.role, u.is_active, u.mfa_enabled, u.mfa_secret, c.password_hash
  from app_user u
  join app_user_credential c on c.user_id = u.id
  where u.email = p_email;
$$;

revoke all on function fn_authenticate_lookup(citext) from public;
grant execute on function fn_authenticate_lookup(citext) to app_runtime;
