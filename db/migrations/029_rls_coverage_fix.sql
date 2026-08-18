-- ============================================================
-- 029_rls_coverage_fix.sql
-- Systematic audit of RLS coverage across every table found 18
-- with RLS disabled. 5 are genuinely global reference/platform
-- data with no tenant relationship at all (caro_clause, ifc_control,
-- rule, rule_version, integration_provider) — correctly exempt.
--
-- The other 13 hold real client/tenant data and had NO database-
-- level tenant isolation at all — protected only by whatever WHERE
-- clause application code happened to include, which is exactly
-- the "defense only in the application layer" pattern RLS exists
-- to protect against (the original design principle stated back in
-- Phase 2: "even if application code has a bug, RLS protects the
-- data"). Most seriously, this included audit_trail_event itself —
-- the audit log had no tenant isolation.
-- ============================================================

-- Tables with engagement_id directly: trivial policy reuse.
do $$
declare t text;
begin
  foreach t in array array[
    'payment', 'receipt', 'credit_debit_note', 'purchase_order', 'grn', 'return_filing',
    'journal_line'  -- has journal_id, not engagement_id directly — handled specially below
  ]
  loop
    if t = 'journal_line' then
      continue;
    end if;
    execute format('alter table %1$s enable row level security;', t);
    execute format(
      'create policy %1$s_isolation on %1$s using (fn_engagement_in_current_firm(engagement_id));', t
    );
  end loop;
end $$;

-- journal_line: scoped via journal_id -> journal.engagement_id
alter table journal_line enable row level security;
create policy journal_line_isolation on journal_line
  using (exists (
    select 1 from journal j where j.id = journal_line.journal_id
      and fn_engagement_in_current_firm(j.engagement_id)
  ));

-- audit_evidence: scoped via procedure_id -> audit_procedure.engagement_id
alter table audit_evidence enable row level security;
create policy audit_evidence_isolation on audit_evidence
  using (exists (
    select 1 from audit_procedure ap where ap.id = audit_evidence.procedure_id
      and fn_engagement_in_current_firm(ap.engagement_id)
  ));

-- working_paper_evidence / working_paper_exception: junction tables,
-- scoped via working_paper_id -> working_paper.engagement_id
alter table working_paper_evidence enable row level security;
create policy working_paper_evidence_isolation on working_paper_evidence
  using (exists (
    select 1 from working_paper wp where wp.id = working_paper_evidence.working_paper_id
      and fn_engagement_in_current_firm(wp.engagement_id)
  ));

alter table working_paper_exception enable row level security;
create policy working_paper_exception_isolation on working_paper_exception
  using (exists (
    select 1 from working_paper wp where wp.id = working_paper_exception.working_paper_id
      and fn_engagement_in_current_firm(wp.engagement_id)
  ));

-- extracted_field: scoped via document_id -> document.engagement_id
alter table extracted_field enable row level security;
create policy extracted_field_isolation on extracted_field
  using (exists (
    select 1 from document d where d.id = extracted_field.document_id
      and fn_engagement_in_current_firm(d.engagement_id)
  ));

-- reconciliation_match / reconciliation_exception: scoped via
-- run_id -> reconciliation_run.engagement_id
alter table reconciliation_match enable row level security;
create policy reconciliation_match_isolation on reconciliation_match
  using (exists (
    select 1 from reconciliation_run r where r.id = reconciliation_match.run_id
      and fn_engagement_in_current_firm(r.engagement_id)
  ));

alter table reconciliation_exception enable row level security;
create policy reconciliation_exception_isolation on reconciliation_exception
  using (exists (
    select 1 from reconciliation_run r where r.id = reconciliation_exception.run_id
      and fn_engagement_in_current_firm(r.engagement_id)
  ));

-- audit_trail_event: the audit log itself. Scoped via firm_id directly
-- (already a column on this table), matching the firm/app_user pattern.
alter table audit_trail_event enable row level security;
create policy audit_trail_event_isolation on audit_trail_event
  using (firm_id = current_setting('app.current_firm_id', true)::uuid);

grant select, insert, update, delete on
  payment, receipt, credit_debit_note, purchase_order, grn, return_filing, journal_line,
  audit_evidence, working_paper_evidence, working_paper_exception, extracted_field,
  reconciliation_match, reconciliation_exception, audit_trail_event
to app_runtime;
