-- ============================================================
-- 004_statutory.sql
-- GST/TDS/PF/ESI/Income Tax source data: returns, challans,
-- statutory liabilities and their roll-forward.
-- ============================================================

create type statutory_type as enum ('GST', 'TDS', 'TCS', 'PF', 'ESI', 'PT', 'INCOME_TAX', 'MCA');

create table return_filing (             -- GSTR-1/3B, TDS 24Q/26Q, PF ECR, etc.
  id             uuid primary key default gen_random_uuid(),
  engagement_id  uuid not null references engagement(id) on delete cascade,
  statutory_type statutory_type not null,
  return_code    text not null,           -- 'GSTR1' / 'GSTR3B' / 'GSTR2B' / '24Q' / '26Q' / 'ECR'
  period         text not null,           -- 'Mar-2026' or 'Q4-FY26'
  filed_date     date,
  due_date       date,
  ack_reference  text,
  raw_payload    jsonb,                   -- normalized line-items live in gst_transaction/tds_transaction below
  created_at     timestamptz not null default now(),
  unique (engagement_id, statutory_type, return_code, period)
);
create index idx_return_engagement on return_filing(engagement_id, statutory_type, period);

create table gst_transaction (           -- normalized invoice-level line from books, GSTR-1, or GSTR-2B
  id             uuid primary key default gen_random_uuid(),
  engagement_id  uuid not null references engagement(id) on delete cascade,
  source         text not null,           -- 'BOOKS' / 'GSTR1' / 'GSTR3B' / 'GSTR2B' / 'EINVOICE' / 'EWAYBILL'
  period         text not null,
  gstin          citext,
  document_no    text,
  document_date  date,
  party_name     text,
  taxable_value  numeric(18,2) not null default 0,
  cgst           numeric(18,2) not null default 0,
  sgst           numeric(18,2) not null default 0,
  igst           numeric(18,2) not null default 0,
  cess           numeric(18,2) not null default 0,
  invoice_id     uuid references invoice(id),
  created_at     timestamptz not null default now()
);
create index idx_gst_txn_engagement on gst_transaction(engagement_id, source, period);
create index idx_gst_txn_docno on gst_transaction(engagement_id, document_no);
create index idx_gst_txn_gstin on gst_transaction(gstin);

create table tds_transaction (
  id             uuid primary key default gen_random_uuid(),
  engagement_id  uuid not null references engagement(id) on delete cascade,
  source         text not null,           -- 'LEDGER' / 'CHALLAN' / 'RETURN' / 'FORM26AS' / 'AIS'
  section        text not null,           -- '194C', '194J', '195', ...
  quarter        text,
  assessment_year text,
  deductee_pan   citext,
  deductee_name  text,
  amount_paid_credited numeric(18,2),
  tds_amount     numeric(18,2) not null default 0,
  deduction_date date,
  payment_date   date,
  created_at     timestamptz not null default now()
);
create index idx_tds_txn_engagement on tds_transaction(engagement_id, section, quarter);
create index idx_tds_txn_pan on tds_transaction(deductee_pan);

create table challan (
  id             uuid primary key default gen_random_uuid(),
  engagement_id  uuid not null references engagement(id) on delete cascade,
  statutory_type statutory_type not null,
  challan_no     text,                    -- CPIN/CIN/BSR+serial as applicable
  bsr_code       text,
  challan_date   date,
  amount         numeric(18,2) not null,
  tax_head       text,                    -- CGST/SGST/IGST/CESS/INTEREST/PENALTY or TDS section
  bank_reference text,
  bank_txn_id    uuid references bank_transaction(id),
  match_status   text default 'UNMATCHED',   -- MATCHED / PARTIALLY_MATCHED / UNMATCHED / POTENTIAL_ERROR
  created_at     timestamptz not null default now()
);
create index idx_challan_engagement on challan(engagement_id, statutory_type);
create index idx_challan_match_status on challan(match_status);

create table statutory_liability (
  id             uuid primary key default gen_random_uuid(),
  engagement_id  uuid not null references engagement(id) on delete cascade,
  statutory_type statutory_type not null,
  period         text not null,
  opening_balance numeric(18,2) not null default 0,
  current_period_liability numeric(18,2) not null default 0,
  payments       numeric(18,2) not null default 0,
  adjustments    numeric(18,2) not null default 0,
  closing_balance numeric(18,2) generated always as
    (opening_balance + current_period_liability - payments - adjustments) stored,
  gl_closing_balance numeric(18,2),        -- from account/trial_balance_line, for comparison
  due_date       date,
  paid_date      date,
  -- Ageing depends on current_date, which Postgres will not allow inside a
  -- generated column (must be immutable). Compute ageing in a view instead
  -- (see v_statutory_dues_ageing at the bottom of this file).
  interest_estimate numeric(18,2) default 0,
  penalty_estimate  numeric(18,2) default 0,
  created_at     timestamptz not null default now(),
  unique (engagement_id, statutory_type, period)
);
create index idx_stat_liability_engagement on statutory_liability(engagement_id, statutory_type);

create table compliance_calendar_item (
  id             uuid primary key default gen_random_uuid(),
  engagement_id  uuid not null references engagement(id) on delete cascade,
  statutory_type statutory_type not null,
  filing_or_payment text not null,        -- 'GSTR-3B' / 'TDS Payment' / 'PF ECR' ...
  period         text not null,
  due_date       date not null,
  actual_date    date,
  delay_days     integer generated always as
    (case when actual_date is null then null else (actual_date - due_date) end) stored,
  amount         numeric(18,2),
  interest       numeric(18,2) default 0,
  penalty        numeric(18,2) default 0,
  status         text default 'PENDING',   -- PENDING / FILED_ON_TIME / FILED_LATE / OVERDUE
  evidence_document_id uuid                -- fk added in 006
);
create index idx_calendar_engagement on compliance_calendar_item(engagement_id, due_date);

-- Statutory Dues Ageing (Section 76). A view rather than a generated column
-- since ageing is relative to "today", not a fixed fact about the row.
create view v_statutory_dues_ageing as
select
  sl.*,
  case when sl.paid_date is not null then null
       else (current_date - sl.due_date) end as age_days,
  case
    when sl.paid_date is not null then null
    when (current_date - sl.due_date) <= 30 then '0–30'
    when (current_date - sl.due_date) <= 60 then '31–60'
    when (current_date - sl.due_date) <= 90 then '61–90'
    when (current_date - sl.due_date) <= 180 then '91–180'
    when (current_date - sl.due_date) <= 365 then '181–365'
    else '>365'
  end as ageing_bucket
from statutory_liability sl
where sl.closing_balance > 0;
