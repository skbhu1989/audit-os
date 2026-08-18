-- ============================================================
-- 017_payroll_statutory.sql
-- Phase 11 (partial): PF/ESI/PT reconciliation needs a payroll
-- fact table — the existing `employee` table (migration 002) is
-- master data only, with nowhere to record period-wise gross
-- salary and statutory contributions.
-- ============================================================

alter type dataset_type add value 'EMPLOYEE_MASTER';
alter type dataset_type add value 'PAYROLL_REGISTER';
alter type dataset_type add value 'PF_CHALLAN';
alter type dataset_type add value 'ESI_CHALLAN';
alter type dataset_type add value 'PT_CHALLAN';

create table payroll_line (
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  employee_id     uuid references employee(id),
  period          text not null,            -- 'Apr-2025' etc, matches the reconciliation engine's period label
  gross_salary    numeric(18,2) not null default 0,
  pf_employee     numeric(18,2) not null default 0,
  pf_employer     numeric(18,2) not null default 0,
  esi_employee    numeric(18,2) not null default 0,
  esi_employer    numeric(18,2) not null default 0,
  pt_amount       numeric(18,2) not null default 0,
  ingestion_run_id uuid references ingestion_run(id),
  created_at      timestamptz not null default now()
);
create index idx_payroll_line_engagement on payroll_line(engagement_id, period);
create index idx_payroll_line_employee on payroll_line(employee_id);

alter table payroll_line enable row level security;
create policy payroll_line_isolation on payroll_line
  using (fn_engagement_in_current_firm(engagement_id));

grant select, insert, update, delete on payroll_line to app_runtime;
