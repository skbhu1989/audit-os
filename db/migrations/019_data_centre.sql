-- ============================================================
-- 019_data_centre.sql
-- Pre-Audit Module Phase 1: the Data Centre's core distinction
-- (Section 39) — "no GST file uploaded" and "GST file uploaded,
-- reconciles with zero exceptions" must never look the same.
-- Nothing in the schema so far tracks *what a dataset type could
-- have but doesn't have* — ingestion_run only exists per upload,
-- so an engagement with zero GST uploads has zero rows, not a
-- visible "0% coverage" signal.
-- ============================================================

create table data_coverage (
  id                uuid primary key default gen_random_uuid(),
  engagement_id     uuid not null references engagement(id) on delete cascade,
  dataset_type      dataset_type not null,
  period            text not null,           -- 'Apr-2025' etc — coverage is tracked per period, not just per dataset
  status            text not null default 'NOT_UPLOADED'
    check (status in ('NOT_UPLOADED','PARTIAL','UPLOADED','NOT_APPLICABLE')),
  latest_ingestion_run_id uuid references ingestion_run(id),
  updated_at        timestamptz not null default now(),
  unique (engagement_id, dataset_type, period)
);
create index idx_data_coverage_engagement on data_coverage(engagement_id);

alter table data_coverage enable row level security;
create policy data_coverage_isolation on data_coverage using (fn_engagement_in_current_firm(engagement_id));
grant select, insert, update, delete on data_coverage to app_runtime;

-- ---------- audit_exception status expansion ----------
-- Section 60's exception lifecycle (OPEN/ASSIGNED/IN PROGRESS/CLIENT
-- RESPONSE/UNDER REVIEW/RESOLVED/WAIVED/CARRIED FORWARD) is richer than
-- the original exception_status enum (Phase 2) built for pure audit
-- exceptions. Extending rather than replacing — existing rows keep
-- their current values, which remain valid members of the enum.
alter type exception_status add value 'ASSIGNED';
alter type exception_status add value 'IN_PROGRESS';
alter type exception_status add value 'CLIENT_RESPONSE';
alter type exception_status add value 'WAIVED';
alter type exception_status add value 'CARRIED_FORWARD';

alter table audit_exception add column due_date date;
alter table audit_exception add column module text;  -- 'GST' / 'TDS' / 'BANK' / 'AP' / 'AR' / etc — Section 60's "Module" field
