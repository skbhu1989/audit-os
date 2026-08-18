-- ============================================================
-- 010_audit_trail_and_rls.sql
-- Append-only audit trail (Section 92) and row-level security
-- for firm/client/engagement tenant isolation (Section 11).
-- ============================================================

create table audit_trail_event (
  id              bigserial primary key,
  firm_id         uuid not null,
  engagement_id   uuid,
  entity_table    text not null,
  entity_id       uuid not null,
  action          text not null,           -- INSERT / UPDATE / DELETE / STATUS_CHANGE / AI_DECISION / OVERRIDE
  actor_id        uuid references app_user(id),
  actor_type      text default 'HUMAN',    -- HUMAN / AI / SYSTEM
  occurred_at     timestamptz not null default now(),
  diff            jsonb                    -- { before: {...}, after: {...} }
);
create index idx_audit_trail_entity on audit_trail_event(entity_table, entity_id);
create index idx_audit_trail_engagement on audit_trail_event(engagement_id, occurred_at);

-- Generic trigger function: logs INSERT/UPDATE/DELETE on any table that has
-- the `engagement_id` column, resolving `firm_id` via engagement -> client -> firm.
create or replace function fn_log_audit_trail() returns trigger as $$
declare
  v_firm_id uuid;
  v_engagement_id uuid;
begin
  v_engagement_id := coalesce(NEW.engagement_id, OLD.engagement_id);
  select c.firm_id into v_firm_id
    from engagement e join client c on c.id = e.client_id
    where e.id = v_engagement_id;

  insert into audit_trail_event (firm_id, engagement_id, entity_table, entity_id, action, diff)
  values (
    v_firm_id, v_engagement_id, TG_TABLE_NAME,
    coalesce(NEW.id, OLD.id),
    TG_OP,
    jsonb_build_object('before', to_jsonb(OLD), 'after', to_jsonb(NEW))
  );
  return coalesce(NEW, OLD);
end;
$$ language plpgsql;

-- Attach to the tables where change history is most audit-critical.
-- (Extend this list as additional tables are added; kept explicit rather
--  than "all tables" so noisy staging/log tables don't bloat the trail.)
do $$
declare t text;
begin
  foreach t in array array[
    'trial_balance_line','journal','statutory_liability',
    'audit_exception','audit_query','working_paper',
    'rule_version','client_gstin'
    -- NOTE: journal_line and reconciliation_match intentionally excluded —
    -- neither has an engagement_id column (only journal_id / run_id
    -- respectively), so they don't fit this generic trigger's assumption.
    -- See migrations 014 and 016 for their dedicated trigger functions.
    -- (Both caught by testing real uploads/reconciliation runs, not by
    -- reading this list.)
  ]
  loop
    execute format(
      'create trigger trg_audit_%1$s after insert or update or delete on %1$s
       for each row execute function fn_log_audit_trail();', t
    );
  end loop;
end $$;

-- ---------- Row-Level Security ----------
-- Application connects with a session variable set per request:
--   set local app.current_firm_id = '<uuid>';
-- Every tenant-scoped table's policy compares against this session variable,
-- enforced regardless of any bug in the application query layer.

alter table client enable row level security;
create policy client_isolation on client
  using (firm_id = current_setting('app.current_firm_id', true)::uuid);

alter table engagement enable row level security;
create policy engagement_isolation on engagement
  using (exists (
    select 1 from client c where c.id = engagement.client_id
      and c.firm_id = current_setting('app.current_firm_id', true)::uuid
  ));

-- Repeat the same pattern for every engagement-scoped table by joining
-- through engagement_id -> engagement -> client -> firm. Example for
-- trial_balance_line; the same policy body is applied to journal,
-- reconciliation_run, audit_exception, working_paper, document, etc.
create or replace function fn_engagement_in_current_firm(p_engagement_id uuid) returns boolean as $$
  select exists (
    select 1 from engagement e join client c on c.id = e.client_id
    where e.id = p_engagement_id
      and c.firm_id = current_setting('app.current_firm_id', true)::uuid
  );
$$ language sql stable;

do $$
declare t text;
begin
  foreach t in array array[
    'account','trial_balance_line','journal','vendor','customer','employee',
    'invoice','bank_transaction','gst_transaction','tds_transaction','challan',
    'statutory_liability','compliance_calendar_item','fixed_asset','inventory_item',
    'loan','investment','share_capital_entry','related_party','document',
    'evidence_edge','audit_procedure','audit_exception','audit_query',
    'working_paper','reconciliation_run'
  ]
  loop
    execute format('alter table %1$s enable row level security;', t);
    execute format(
      'create policy %1$s_isolation on %1$s using (fn_engagement_in_current_firm(engagement_id));', t
    );
  end loop;
end $$;
