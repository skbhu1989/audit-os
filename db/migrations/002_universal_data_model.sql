-- ============================================================
-- 002_universal_data_model.sql
-- Chart of accounts, trial balance, journals/journal lines,
-- and party masters (vendor/customer/employee) — the spine
-- every sub-ledger and reconciliation module reads from.
-- ============================================================

create type fs_statement as enum ('BALANCE_SHEET', 'PROFIT_AND_LOSS', 'CASH_FLOW', 'EQUITY_CHANGES', 'UNMAPPED');

create table account (                  -- chart of accounts, one row per unique ledger head
  id            uuid primary key default gen_random_uuid(),
  engagement_id uuid not null references engagement(id) on delete cascade,
  ledger_name   text not null,
  account_head  text,                    -- e.g. 'Current Liabilities'
  fs_statement  fs_statement not null default 'UNMAPPED',
  fs_line       text,                    -- e.g. 'Balance Sheet — Current Liabilities'
  note_ref      text,
  is_suspense   boolean not null default false,
  mapped_by     uuid references app_user(id),
  mapped_at     timestamptz,
  created_at    timestamptz not null default now(),
  unique (engagement_id, ledger_name)
);
create index idx_account_engagement on account(engagement_id);
create index idx_account_fs_line on account(fs_line);

create table trial_balance_line (       -- one row per ledger per period-end (supports multiple TB pulls)
  id            uuid primary key default gen_random_uuid(),
  engagement_id uuid not null references engagement(id) on delete cascade,
  account_id    uuid not null references account(id),
  as_of_date    date not null,
  debit         numeric(18,2) not null default 0,
  credit        numeric(18,2) not null default 0,
  flag          text,                    -- e.g. 'Suspense balance — requires classification'
  source_file_id uuid,                   -- fk added in 006 (document)
  created_at    timestamptz not null default now()
);
create index idx_tb_engagement_date on trial_balance_line(engagement_id, as_of_date);

create type risk_level as enum ('LOW', 'MODERATE', 'MEDIUM', 'HIGH', 'CRITICAL');

create table journal (
  id             uuid primary key default gen_random_uuid(),
  engagement_id  uuid not null references engagement(id) on delete cascade,
  journal_no     text,
  posted_date    date not null,
  posted_by      text,                   -- as recorded in source system (free text; not necessarily app_user)
  narration      text,
  source_system  text,                   -- Tally / SAP / Zoho / manual upload
  amount         numeric(18,2) not null, -- total debit (= total credit) for the journal
  risk_score     numeric(5,2),
  risk_level     risk_level,
  risk_reasons   text[],
  is_manual      boolean not null default true,
  created_at     timestamptz not null default now()
);
create index idx_journal_engagement_date on journal(engagement_id, posted_date);
create index idx_journal_risk on journal(engagement_id, risk_level);

create table journal_line (
  id            uuid primary key default gen_random_uuid(),
  journal_id    uuid not null references journal(id) on delete cascade,
  account_id    uuid not null references account(id),
  debit         numeric(18,2) not null default 0,
  credit        numeric(18,2) not null default 0,
  line_narration text,
  check (debit = 0 or credit = 0)        -- a line is either a debit or a credit, never both
);
create index idx_journal_line_journal on journal_line(journal_id);
create index idx_journal_line_account on journal_line(account_id);

-- ---------- party masters ----------

create table vendor (
  id            uuid primary key default gen_random_uuid(),
  engagement_id uuid not null references engagement(id) on delete cascade,
  name          text not null,
  gstin         citext,
  pan           citext,
  bank_account_masked text,
  address       text,
  is_related_party boolean not null default false,
  dup_of_vendor_id uuid references vendor(id),  -- set by master data consistency engine
  created_at    timestamptz not null default now()
);
create index idx_vendor_engagement on vendor(engagement_id);
create index idx_vendor_gstin on vendor(gstin);
create index idx_vendor_pan on vendor(pan);

create table customer (
  id            uuid primary key default gen_random_uuid(),
  engagement_id uuid not null references engagement(id) on delete cascade,
  name          text not null,
  gstin         citext,
  pan           citext,
  address       text,
  is_related_party boolean not null default false,
  dup_of_customer_id uuid references customer(id),
  created_at    timestamptz not null default now()
);
create index idx_customer_engagement on customer(engagement_id);
create index idx_customer_gstin on customer(gstin);

create table employee (
  id            uuid primary key default gen_random_uuid(),
  engagement_id uuid not null references engagement(id) on delete cascade,
  employee_code text,
  name          text not null,
  pan           citext,
  uan           text,                    -- PF Universal Account Number
  bank_account_masked text,
  date_of_joining date,
  date_of_exit  date,
  created_at    timestamptz not null default now(),
  unique (engagement_id, employee_code)
);
create index idx_employee_engagement on employee(engagement_id);
