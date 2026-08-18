-- ============================================================
-- 028_audit_trigger_systematic_fix.sql
-- A systematic audit of every table wired to the generic
-- fn_log_audit_trail() (which assumes an engagement_id column
-- exists directly on the row) found two more latent instances of
-- the same bug class fixed four times before (client, engagement,
-- journal_line, reconciliation_match — migrations 011/014/016):
--
-- 1. client_gstin: no engagement_id (scoped via client_id ->
--    client.firm_id). This bug was NEVER caught by feature testing
--    because no endpoint to add a second GSTIN to a client was ever
--    built — the write path simply never ran. Found by checking
--    every trigger-table pairing systematically, not by testing a
--    feature that happened to touch it.
--
-- 2. rule_version: genuinely platform-level reference data (no
--    firm_id or engagement_id anywhere in its lineage — rule_code
--    -> rule, no tenant relationship at all). audit_trail_event.firm_id
--    is NOT NULL, so this table structurally cannot be logged into
--    the tenant-scoped audit trail — not a bug to patch with a fake
--    firm_id, but a real architectural gap: platform-level reference
--    data needs its own separate changelog mechanism, which does not
--    exist in this system. Removed from this trigger entirely rather
--    than hacked around.
-- ============================================================

drop trigger if exists trg_audit_client_gstin on client_gstin;

create or replace function fn_log_audit_trail_client_gstin() returns trigger as $$
declare
  v_firm_id uuid;
begin
  select c.firm_id into v_firm_id from client c where c.id = coalesce(NEW.client_id, OLD.client_id);
  insert into audit_trail_event (firm_id, engagement_id, entity_table, entity_id, action, diff)
  values (
    v_firm_id, null, 'client_gstin', coalesce(NEW.id, OLD.id), TG_OP,
    jsonb_build_object('before', to_jsonb(OLD), 'after', to_jsonb(NEW))
  );
  return coalesce(NEW, OLD);
end;
$$ language plpgsql;

create trigger trg_audit_client_gstin after insert or update or delete on client_gstin
  for each row execute function fn_log_audit_trail_client_gstin();

drop trigger if exists trg_audit_rule_version on rule_version;
-- No replacement trigger: rule_version changes are not logged to
-- audit_trail_event at all until a platform-level changelog mechanism
-- is built (see comment above). Documented as a known gap, not silently
-- dropped without explanation.
