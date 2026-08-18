-- ============================================================
-- 008_reconciliation.sql
-- Shared reconciliation engine tables used by every statutory
-- and bank reconciliation module (Section AZ matching hierarchy).
-- ============================================================

create type match_level as enum (
  'L1_EXACT_ID','L2_DOC_PLUS_PARTY_ID','L3_AMOUNT_DATE_PARTY',
  'L4_AMOUNT_PARTY_PERIOD','L5_FUZZY','L6_AI_ASSISTED'
);
create type match_status as enum ('MATCHED','PARTIALLY_MATCHED','UNMATCHED','POTENTIAL_ERROR');
create type match_action as enum ('ACCEPT','REJECT','MODIFY','MERGE','SPLIT');

create table reconciliation_run (
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  recon_type      text not null,           -- 'GST_BOOKS_VS_SALES_REGISTER' / 'GST_GSTR1_VS_GSTR3B' /
                                            -- 'TDS_LEDGER_VS_CHALLAN' / 'BANK_STATEMENT_VS_LEDGER' / ...
  period          text not null,
  source_a_desc   text,
  source_b_desc   text,
  run_at          timestamptz not null default now(),
  run_by          uuid references app_user(id),
  total_records   integer,
  matched_count   integer,
  partial_count   integer,
  unmatched_count integer
);
create index idx_recon_run_engagement on reconciliation_run(engagement_id, recon_type, period);

create table reconciliation_match (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null references reconciliation_run(id) on delete cascade,
  source_a_entity_type text not null,      -- e.g. 'gst_transaction', 'challan', 'bank_transaction'
  source_a_entity_id   uuid not null,
  source_b_entity_type text,
  source_b_entity_id   uuid,
  match_level     match_level,
  match_status    match_status not null,
  confidence_score numeric(5,4),           -- 0.0000–1.0000, populated for L5/L6
  matching_factors text[],                 -- ['Vendor GSTIN','Invoice number','Invoice value', ...]
  amount_a        numeric(18,2),
  amount_b        numeric(18,2),
  difference      numeric(18,2) generated always as (coalesce(amount_a,0) - coalesce(amount_b,0)) stored,
  auditor_action  match_action,
  actioned_by     uuid references app_user(id),
  actioned_at     timestamptz,
  created_at      timestamptz not null default now()
);
create index idx_recon_match_run on reconciliation_match(run_id, match_status);
create index idx_recon_match_source_a on reconciliation_match(source_a_entity_type, source_a_entity_id);

-- Detailed, reportable exception rows (Section 59's required column set),
-- generated from reconciliation_match rows where status <> MATCHED.
create table reconciliation_exception (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null references reconciliation_run(id) on delete cascade,
  match_id        uuid references reconciliation_match(id),
  period          text,
  gstin           citext,
  document_no     text,
  document_date   date,
  party_name      text,
  taxable_value   numeric(18,2),
  cgst            numeric(18,2),
  sgst            numeric(18,2),
  igst            numeric(18,2),
  cess            numeric(18,2),
  books_amount    numeric(18,2),
  return_amount   numeric(18,2),
  difference      numeric(18,2),
  reason          text,
  risk_level      risk_level not null default 'LOW',
  suggested_action text,
  audit_exception_id uuid references audit_exception(id)   -- links into the central exception hub (007)
);
create index idx_recon_exception_run on reconciliation_exception(run_id);
create index idx_recon_exception_risk on reconciliation_exception(risk_level);
