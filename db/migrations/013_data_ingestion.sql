-- ============================================================
-- 013_data_ingestion.sql
-- Tracks every file ingested (Section L/N: Data Import + Validation
-- Engine) so a Data Quality Score and exception report can be shown
-- per upload, and every row written to the Universal Data Model is
-- traceable back to the file/run that produced it.
-- ============================================================

create type dataset_type as enum (
  'TRIAL_BALANCE', 'GENERAL_LEDGER', 'VENDOR_MASTER', 'CUSTOMER_MASTER',
  'SALES_REGISTER', 'PURCHASE_REGISTER', 'BANK_STATEMENT'
);
create type ingestion_status as enum ('PROCESSING', 'COMPLETED', 'COMPLETED_WITH_WARNINGS', 'FAILED');
create type exception_severity as enum ('WARNING', 'ERROR');

create table ingestion_run (
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  document_id     uuid references document(id),
  dataset_type    dataset_type not null,
  file_name       text not null,
  status          ingestion_status not null default 'PROCESSING',
  rows_total      integer not null default 0,
  rows_valid      integer not null default 0,
  rows_rejected   integer not null default 0,
  data_quality_score numeric(5,2),          -- 0-100, see app/ingestion.py:compute_quality_score
  started_at      timestamptz not null default now(),
  completed_at    timestamptz,
  started_by      uuid references app_user(id)
);
create index idx_ingestion_run_engagement on ingestion_run(engagement_id, dataset_type);

create table ingestion_exception (
  id              uuid primary key default gen_random_uuid(),
  ingestion_run_id uuid not null references ingestion_run(id) on delete cascade,
  row_number      integer,                  -- 1-based, as it appeared in the source file
  field           text,
  message         text not null,
  severity        exception_severity not null,
  raw_row         jsonb                     -- the offending row as parsed, for drill-down
);
create index idx_ingestion_exception_run on ingestion_exception(ingestion_run_id, severity);

-- Link trial_balance_line rows back to the ingestion run that created them
-- (source_file_id already links to the document; this adds the run for
-- "which parse attempt produced this row" when a client re-uploads a
-- corrected file and old/new rows need to be told apart).
alter table trial_balance_line add column ingestion_run_id uuid references ingestion_run(id);
alter table journal add column ingestion_run_id uuid references ingestion_run(id);
alter table vendor add column ingestion_run_id uuid references ingestion_run(id);
alter table customer add column ingestion_run_id uuid references ingestion_run(id);

alter table ingestion_run enable row level security;
create policy ingestion_run_isolation on ingestion_run
  using (fn_engagement_in_current_firm(engagement_id));

alter table ingestion_exception enable row level security;
create policy ingestion_exception_isolation on ingestion_exception
  using (exists (
    select 1 from ingestion_run r where r.id = ingestion_exception.ingestion_run_id
      and fn_engagement_in_current_firm(r.engagement_id)
  ));

grant select, insert, update, delete on ingestion_run, ingestion_exception to app_runtime;
