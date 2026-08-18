-- ============================================================
-- 021_month_end_close.sql
-- Section 59: close workflow with per-task status/owner/reviewer/
-- due date/evidence, distinguishing system-computed status (pulled
-- live from the reconciliation engines already built) from tasks
-- that need a human status update because no engine computes them yet.
-- ============================================================

create table month_end_close_task (
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  period          text not null,
  category        text not null,           -- 'Bank' / 'GST' / 'TDS' / 'AP' / 'AR' / 'Payroll' / 'Fixed Assets' / etc
  task_name       text not null,
  is_system_computed boolean not null default false,
  status          text not null default 'NOT_STARTED'
    check (status in ('NOT_STARTED','IN_PROGRESS','REVIEW_REQUIRED','COMPLETE','NOT_APPLICABLE')),
  owner_id        uuid references app_user(id),
  reviewer_id     uuid references app_user(id),
  due_date        date,
  evidence_note   text,
  updated_at      timestamptz not null default now(),
  unique (engagement_id, period, category, task_name)
);
create index idx_month_end_close_engagement on month_end_close_task(engagement_id, period);

alter table month_end_close_task enable row level security;
create policy month_end_close_task_isolation on month_end_close_task using (fn_engagement_in_current_firm(engagement_id));
grant select, insert, update, delete on month_end_close_task to app_runtime;
