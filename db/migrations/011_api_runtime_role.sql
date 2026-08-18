-- ============================================================
-- 011_api_runtime_role.sql
-- Phase 3 additions: RLS on the tables the Auth/Client/Engagement
-- API touches that Migration 010 missed, plus a least-privilege
-- database role for the API service to connect as (never the
-- table owner — RLS is bypassed for owners/superusers).
-- ============================================================

-- firm: a session should only ever see/modify its own firm row for
-- SELECT/UPDATE/DELETE. INSERT is intentionally permissive: creating a
-- brand-new firm (signup) is the one operation that must work with no
-- tenant context set yet — there is no existing firm_id to check against.
-- The API sets `app.current_firm_id` to the newly created firm's id
-- immediately afterwards, inside the same transaction, before inserting
-- the admin user — so app_user's INSERT policy applies normally.
alter table firm enable row level security;
create policy firm_select on firm for select
  using (id = current_setting('app.current_firm_id', true)::uuid);
create policy firm_update on firm for update
  using (id = current_setting('app.current_firm_id', true)::uuid);
create policy firm_delete on firm for delete
  using (id = current_setting('app.current_firm_id', true)::uuid);
create policy firm_insert on firm for insert
  with check (true);

-- app_user: scoped directly by firm_id (no engagement_id hop needed).
-- Strict on every command, including INSERT — by the time a user is
-- created, the firm already exists and the transaction has set context.
alter table app_user enable row level security;
create policy app_user_select on app_user for select
  using (firm_id = current_setting('app.current_firm_id', true)::uuid);
create policy app_user_update on app_user for update
  using (firm_id = current_setting('app.current_firm_id', true)::uuid);
create policy app_user_delete on app_user for delete
  using (firm_id = current_setting('app.current_firm_id', true)::uuid);
create policy app_user_insert on app_user for insert
  with check (firm_id = current_setting('app.current_firm_id', true)::uuid);

-- client_gstin: scoped via client -> firm.
create or replace function fn_client_in_current_firm(p_client_id uuid) returns boolean as $$
  select exists (
    select 1 from client c
    where c.id = p_client_id
      and c.firm_id = current_setting('app.current_firm_id', true)::uuid
  );
$$ language sql stable;

alter table client_gstin enable row level security;
create policy client_gstin_isolation on client_gstin
  using (fn_client_in_current_firm(client_id));

-- period and engagement_team: engagement_id-scoped, same pattern as 010's loop
-- (kept as explicit statements here since 010's loop had already run).
alter table period enable row level security;
create policy period_isolation on period
  using (fn_engagement_in_current_firm(engagement_id));

alter table engagement_team enable row level security;
create policy engagement_team_isolation on engagement_team
  using (fn_engagement_in_current_firm(engagement_id));

-- Attach the audit trail trigger to the Phase 3 write-heavy tables too.
-- `client` and `engagement` don't fit fn_log_audit_trail()'s assumption
-- (an `engagement_id` column pointing at a row under an engagement) — client
-- IS the firm-scoped root, and engagement's own `id` is what other tables
-- call `engagement_id`. Each gets its own small trigger function instead of
-- forcing the generic one to handle shapes it wasn't designed for.

create or replace function fn_log_audit_trail_client() returns trigger as $$
begin
  insert into audit_trail_event (firm_id, engagement_id, entity_table, entity_id, action, diff)
  values (
    coalesce(NEW.firm_id, OLD.firm_id), null, 'client', coalesce(NEW.id, OLD.id), TG_OP,
    jsonb_build_object('before', to_jsonb(OLD), 'after', to_jsonb(NEW))
  );
  return coalesce(NEW, OLD);
end;
$$ language plpgsql;

create trigger trg_audit_client after insert or update or delete on client
  for each row execute function fn_log_audit_trail_client();

create or replace function fn_log_audit_trail_engagement() returns trigger as $$
declare
  v_firm_id uuid;
begin
  select c.firm_id into v_firm_id from client c where c.id = coalesce(NEW.client_id, OLD.client_id);
  insert into audit_trail_event (firm_id, engagement_id, entity_table, entity_id, action, diff)
  values (
    v_firm_id, coalesce(NEW.id, OLD.id), 'engagement', coalesce(NEW.id, OLD.id), TG_OP,
    jsonb_build_object('before', to_jsonb(OLD), 'after', to_jsonb(NEW))
  );
  return coalesce(NEW, OLD);
end;
$$ language plpgsql;

create trigger trg_audit_engagement after insert or update or delete on engagement
  for each row execute function fn_log_audit_trail_engagement();

-- ---------- Least-privilege runtime role ----------
-- The API connects as this role, never as the migration-owning role, so that
-- RLS (which is bypassed for table owners and superusers) actually applies.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'app_runtime') then
    create role app_runtime login password 'CHANGE_ME_IN_ENV';
  end if;
end $$;

grant usage on schema public to app_runtime;
grant select, insert, update, delete on all tables in schema public to app_runtime;
grant usage, select on all sequences in schema public to app_runtime;
alter default privileges in schema public grant select, insert, update, delete on tables to app_runtime;
alter default privileges in schema public grant usage, select on sequences to app_runtime;
-- No DELETE/DDL beyond this; schema migrations run as the owning role, never as app_runtime.
