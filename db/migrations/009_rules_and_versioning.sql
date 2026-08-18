-- ============================================================
-- 009_rules_and_versioning.sql
-- Deterministic, effective-dated rules — GST/TDS thresholds and
-- rates, materiality formulas, depreciation tables, due-date
-- calendars. Never hardcoded in application code (Section CH).
-- ============================================================

create extension if not exists btree_gist;   -- required for the exclusion constraint below

create table rule (
  code            text primary key,        -- 'TDS_SECTION_194C_RATE' / 'MATERIALITY_BENCHMARK_DEFAULT'
  category        text not null,           -- 'TDS' / 'GST' / 'MATERIALITY' / 'DEPRECIATION' / 'CALENDAR'
  description     text
);

create table rule_version (
  id              uuid primary key default gen_random_uuid(),
  rule_code       text not null references rule(code),
  logic           jsonb not null,          -- structured params, e.g. { "threshold": 30000, "rate": 0.1 }
  effective_from  date not null,
  effective_to    date,                    -- null = still in force
  source_reference text,                   -- statute/notification citation
  superseded_by_id uuid references rule_version(id),
  created_at      timestamptz not null default now(),
  created_by      uuid references app_user(id),
  constraint no_overlapping_periods
    exclude using gist (
      rule_code with =,
      daterange(effective_from, coalesce(effective_to, 'infinity'::date), '[]') with &&
    )
);
create index idx_rule_version_code_date on rule_version(rule_code, effective_from, effective_to);

-- Example seed rows (illustrative — real data loaded via a maintained rule-content pipeline):
insert into rule (code, category, description) values
  ('TDS_SEC_194C_RATE', 'TDS', 'TDS rate under Section 194C — contractors'),
  ('TDS_SEC_194J_RATE', 'TDS', 'TDS rate under Section 194J — professional/technical fees'),
  ('MATERIALITY_BENCHMARK_DEFAULT', 'MATERIALITY', 'Default overall materiality benchmark and %');

insert into rule_version (rule_code, logic, effective_from, source_reference) values
  ('TDS_SEC_194C_RATE', '{"threshold_single":30000,"threshold_aggregate":100000,"rate_individual":0.01,"rate_other":0.02}', '2020-04-01', 'Income Tax Act 1961, Sec 194C'),
  ('TDS_SEC_194J_RATE', '{"threshold":30000,"rate_professional":0.10,"rate_technical":0.02}', '2020-04-01', 'Income Tax Act 1961, Sec 194J'),
  ('MATERIALITY_BENCHMARK_DEFAULT', '{"benchmark":"PBT","percent":0.05}', '2020-04-01', 'SA 320');
