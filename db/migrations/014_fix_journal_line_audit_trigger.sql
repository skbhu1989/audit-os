-- ============================================================
-- 014_fix_journal_line_audit_trigger.sql
-- migration 010 attached the generic fn_log_audit_trail() trigger to
-- journal_line, but journal_line has no engagement_id column (only
-- journal_id) — every INSERT into journal_line failed with
-- "record NEW has no field engagement_id". Found by actually uploading
-- a general ledger file through the API, not by reading the trigger code.
-- Same fix pattern as fn_log_audit_trail_client/_engagement in 011.
-- ============================================================

drop trigger if exists trg_audit_journal_line on journal_line;

create or replace function fn_log_audit_trail_journal_line() returns trigger as $$
declare
  v_firm_id uuid;
  v_engagement_id uuid;
begin
  select j.engagement_id into v_engagement_id from journal j where j.id = coalesce(NEW.journal_id, OLD.journal_id);
  select c.firm_id into v_firm_id
    from engagement e join client c on c.id = e.client_id
    where e.id = v_engagement_id;

  insert into audit_trail_event (firm_id, engagement_id, entity_table, entity_id, action, diff)
  values (
    v_firm_id, v_engagement_id, 'journal_line', coalesce(NEW.id, OLD.id), TG_OP,
    jsonb_build_object('before', to_jsonb(OLD), 'after', to_jsonb(NEW))
  );
  return coalesce(NEW, OLD);
end;
$$ language plpgsql;

create trigger trg_audit_journal_line after insert or update or delete on journal_line
  for each row execute function fn_log_audit_trail_journal_line();
