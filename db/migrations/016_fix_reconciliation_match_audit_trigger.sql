-- ============================================================
-- 016_fix_reconciliation_match_audit_trigger.sql
-- Same bug class as migrations 011 (client/engagement) and 014
-- (journal_line): migration 010's generic fn_log_audit_trail()
-- trigger was attached to reconciliation_match, which has no
-- engagement_id column (only run_id -> reconciliation_run.engagement_id).
-- Found by running Phase 6's GST reconciliation end-to-end, not by
-- re-reading migration 010's trigger list.
-- ============================================================

drop trigger if exists trg_audit_reconciliation_match on reconciliation_match;

create or replace function fn_log_audit_trail_reconciliation_match() returns trigger as $$
declare
  v_firm_id uuid;
  v_engagement_id uuid;
begin
  select rr.engagement_id into v_engagement_id from reconciliation_run rr where rr.id = coalesce(NEW.run_id, OLD.run_id);
  select c.firm_id into v_firm_id
    from engagement e join client c on c.id = e.client_id
    where e.id = v_engagement_id;

  insert into audit_trail_event (firm_id, engagement_id, entity_table, entity_id, action, diff)
  values (
    v_firm_id, v_engagement_id, 'reconciliation_match', coalesce(NEW.id, OLD.id), TG_OP,
    jsonb_build_object('before', to_jsonb(OLD), 'after', to_jsonb(NEW))
  );
  return coalesce(NEW, OLD);
end;
$$ language plpgsql;

create trigger trg_audit_reconciliation_match after insert or update or delete on reconciliation_match
  for each row execute function fn_log_audit_trail_reconciliation_match();
