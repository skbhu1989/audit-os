-- ============================================================
-- 007_audit_engine.sql
-- Audit procedures, exceptions, client queries, and working
-- papers — the layer that turns findings into documentation.
-- ============================================================

create type fs_assertion as enum (
  'EXISTENCE','COMPLETENESS','ACCURACY','VALUATION','RIGHTS_AND_OBLIGATIONS',
  'CUTOFF','CLASSIFICATION','PRESENTATION','DISCLOSURE'
);

create table audit_procedure (
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  title           text not null,
  objective       text,
  assertions      fs_assertion[] not null,
  applicable_standard text[],              -- ['Ind AS 115','SA 330']
  fs_area         text,                    -- 'Revenue' / 'GST' / 'TDS' / 'Fixed Assets' / ...
  population_desc text,
  sample_desc     text,
  status          text default 'NOT_STARTED', -- NOT_STARTED / IN_PROGRESS / COMPLETE
  conclusion      text,
  created_at      timestamptz not null default now()
);
create index idx_procedure_engagement on audit_procedure(engagement_id, fs_area);

create table audit_evidence (
  id              uuid primary key default gen_random_uuid(),
  procedure_id    uuid not null references audit_procedure(id) on delete cascade,
  document_id     uuid references document(id),
  description     text,
  obtained        boolean not null default false,
  obtained_at     timestamptz
);
create index idx_evidence_procedure on audit_evidence(procedure_id);

create type exception_status as enum (
  'OPEN','UNDER_REVIEW','QUERY_RAISED','CLIENT_RESPONDED','ACCEPTED','ADJUSTED','NOTED','CLOSED'
);

create table audit_exception (           -- the central hub: every reconciliation/JE/analytics flag lands here
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  source_type     text not null,          -- 'RECONCILIATION' / 'JOURNAL_TEST' / 'ANALYTICS' / 'DOCUMENT_AI'
  source_id       uuid,                   -- points to reconciliation_exception.id / journal.id / etc. (polymorphic)
  compliance_type statutory_type,         -- null if not statutory in nature
  period          text,
  fs_area         text,
  amount          numeric(18,2),
  statutory_requirement text,
  difference      numeric(18,2),
  reason          text,
  risk_level      risk_level not null default 'LOW',
  potential_interest numeric(18,2) default 0,
  potential_penalty  numeric(18,2) default 0,
  recommended_action text,
  fs_assertion    fs_assertion[],
  linked_procedure_id uuid references audit_procedure(id),
  owner_id        uuid references app_user(id),
  status          exception_status not null default 'OPEN',
  reviewer_id     uuid references app_user(id),
  resolution      text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create index idx_exception_engagement on audit_exception(engagement_id, status);
create index idx_exception_risk on audit_exception(engagement_id, risk_level);
create index idx_exception_compliance_type on audit_exception(compliance_type);

create table audit_query (
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  exception_id    uuid references audit_exception(id),
  query_text      text not null,           -- AI-drafted, auditor-editable
  required_information text,
  due_date        date,
  status          text default 'OPEN',     -- OPEN / RESPONDED / OVERDUE / CLOSED
  raised_by       uuid references app_user(id),
  raised_at       timestamptz not null default now(),
  client_response text,
  responded_at    timestamptz
);
create index idx_query_engagement on audit_query(engagement_id, status);
create index idx_query_exception on audit_query(exception_id);

create type wp_status as enum ('DRAFT','PREPARED','IN_REVIEW','REVIEWED','APPROVED');

create table working_paper (
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  wp_code         text not null,           -- 'WP-GST-05'
  objective       text not null,
  fs_assertion    fs_assertion[] not null,
  applicable_standard text[],
  procedure_id    uuid references audit_procedure(id),
  population_desc text,
  sample          jsonb,                   -- { method, size, list_ref }
  testing_result  jsonb,                   -- { matched, partially_matched, unmatched }
  conclusion      text,
  preparer_id     uuid references app_user(id),
  prepared_at     timestamptz,
  reviewer_id     uuid references app_user(id),
  reviewed_at     timestamptz,
  approver_id     uuid references app_user(id),
  approved_at     timestamptz,
  status          wp_status not null default 'DRAFT',
  version         integer not null default 1,
  supersedes_wp_id uuid references working_paper(id),
  created_at      timestamptz not null default now(),
  unique (engagement_id, wp_code, version)
);
create index idx_wp_engagement on working_paper(engagement_id, status);

create table working_paper_exception (   -- many-to-many: a WP can cover several exceptions and vice versa
  working_paper_id uuid not null references working_paper(id) on delete cascade,
  exception_id      uuid not null references audit_exception(id) on delete cascade,
  primary key (working_paper_id, exception_id)
);

create table working_paper_evidence (
  working_paper_id uuid not null references working_paper(id) on delete cascade,
  evidence_id       uuid not null references audit_evidence(id) on delete cascade,
  primary key (working_paper_id, evidence_id)
);
