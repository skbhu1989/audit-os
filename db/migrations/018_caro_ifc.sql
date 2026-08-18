-- ============================================================
-- 018_caro_ifc.sql
-- Phase 12: CARO clause tracking and IFC control testing.
-- caro_clause / ifc_control are reference (seed) data, shared
-- across engagements; caro_assessment / ifc_test_result are the
-- engagement-specific work product, with the same sign-off shape
-- as working_paper (Section 50: AI drafts, humans conclude).
-- ============================================================

create table caro_clause (
  clause_no       text primary key,        -- 'i', 'ii', ... 'xxi' (CARO 2020)
  title           text not null,
  topic_summary   text not null,           -- paraphrased topic description, not verbatim statutory text
  default_applicability text not null default 'REQUIRES_ASSESSMENT'
    check (default_applicability in ('LIKELY_APPLICABLE','REQUIRES_ASSESSMENT'))
);

create type assessment_status as enum ('NOT_STARTED', 'DRAFT', 'PREPARED', 'REVIEWED', 'APPROVED');

create table caro_assessment (
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  clause_no       text not null references caro_clause(clause_no),
  applicability   text not null default 'REQUIRES_ASSESSMENT'
    check (applicability in ('APPLICABLE','NOT_APPLICABLE','REQUIRES_ASSESSMENT')),
  data_status     text not null default 'INSUFFICIENT_DATA'
    check (data_status in ('DATA_BACKED','INSUFFICIENT_DATA')),
  draft_response  text,
  data_gap_reason text,
  final_response  text,
  preparer_id     uuid references app_user(id), prepared_at timestamptz,
  reviewer_id     uuid references app_user(id), reviewed_at timestamptz,
  approver_id     uuid references app_user(id), approved_at timestamptz,
  status          assessment_status not null default 'NOT_STARTED',
  updated_at      timestamptz not null default now(),
  unique (engagement_id, clause_no)
);
create index idx_caro_assessment_engagement on caro_assessment(engagement_id);

create table ifc_control (
  id              text primary key,         -- e.g. 'P2P-01'
  process         text not null,            -- 'Procure-to-Pay' / 'Order-to-Cash' / 'Record-to-Report' / 'Treasury'
  control_description text not null,
  control_type    text not null,            -- 'Preventive' / 'Detective'
  frequency       text not null,            -- 'Transaction' / 'Monthly' / 'Quarterly'
  automatable     boolean not null default false  -- can this system derive a test result from ingested data?
);

create table ifc_test_result (
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  control_id      text not null references ifc_control(id),
  test_result     text not null check (test_result in ('EFFECTIVE','EXCEPTION_NOTED','NOT_TESTED')),
  exception_detail text,
  tested_via      text not null default 'MANUAL' check (tested_via in ('AUTOMATED','MANUAL')),
  tested_by       uuid references app_user(id),
  tested_at       timestamptz not null default now(),
  unique (engagement_id, control_id)
);
create index idx_ifc_test_engagement on ifc_test_result(engagement_id);

alter table caro_assessment enable row level security;
create policy caro_assessment_isolation on caro_assessment using (fn_engagement_in_current_firm(engagement_id));
alter table ifc_test_result enable row level security;
create policy ifc_test_result_isolation on ifc_test_result using (fn_engagement_in_current_firm(engagement_id));

grant select, insert, update, delete on caro_assessment, ifc_test_result to app_runtime;
grant select on caro_clause, ifc_control to app_runtime;

-- ---------- Seed data: genuine CARO 2020 clause topics (paraphrased, not
-- verbatim statutory text) and a standard IFC control library (industry-
-- standard control concepts, not fabricated). ----------

insert into caro_clause (clause_no, title, topic_summary, default_applicability) values
  ('i', 'Property, Plant and Equipment and Intangible Assets', 'Fixed asset records, title deeds, revaluation, and pending proceedings under benami property law', 'REQUIRES_ASSESSMENT'),
  ('ii', 'Inventory', 'Physical verification of inventory and working capital bank sanction vs stock statement reconciliation', 'REQUIRES_ASSESSMENT'),
  ('iii', 'Investments, Loans, Guarantees to Related/Other Parties', 'Terms, repayment schedule, and overdue status of loans/advances given', 'REQUIRES_ASSESSMENT'),
  ('iv', 'Sections 185 & 186 Compliance', 'Loans, investments, guarantees, and securities given in compliance with the Companies Act', 'REQUIRES_ASSESSMENT'),
  ('v', 'Deposits', 'Compliance with deposit acceptance provisions and RBI directives', 'REQUIRES_ASSESSMENT'),
  ('vi', 'Cost Records', 'Maintenance of cost records where prescribed under Sec 148', 'REQUIRES_ASSESSMENT'),
  ('vii', 'Statutory Dues', 'Regularity of depositing GST, TDS, PF, ESI, Income Tax and other statutory dues; amounts outstanding beyond 6 months', 'LIKELY_APPLICABLE'),
  ('viii', 'Unrecorded Income', 'Previously unrecorded income surrendered/disclosed during a tax assessment/survey', 'REQUIRES_ASSESSMENT'),
  ('ix', 'Repayment of Borrowings', 'Defaults in repayment of loans/borrowings to any lender', 'LIKELY_APPLICABLE'),
  ('x', 'Utilisation of IPO/Term Loan Proceeds', 'Whether funds raised were applied for the stated purpose', 'REQUIRES_ASSESSMENT'),
  ('xi', 'Fraud Reporting', 'Fraud by or on the company noticed or reported during the year', 'LIKELY_APPLICABLE'),
  ('xii', 'Nidhi Company Compliance', 'Net owned funds, deposit ratios, and default in repayment (Nidhi companies only)', 'REQUIRES_ASSESSMENT'),
  ('xiii', 'Related Party Transactions', 'Compliance with Sections 177 and 188 and disclosure in financial statements', 'LIKELY_APPLICABLE'),
  ('xiv', 'Internal Audit', 'Whether an internal audit system commensurate with the size/nature of business exists', 'REQUIRES_ASSESSMENT'),
  ('xv', 'Non-cash Transactions with Directors', 'Compliance with Section 192 for non-cash transactions with directors/connected persons', 'REQUIRES_ASSESSMENT'),
  ('xvi', 'NBFC Registration', 'Requirement to register under Sec 45-IA of the RBI Act', 'REQUIRES_ASSESSMENT'),
  ('xvii', 'Cash Losses', 'Cash losses incurred in the current and immediately preceding financial year', 'LIKELY_APPLICABLE'),
  ('xviii', 'Auditor Resignation', 'Issues, objections, or concerns raised by outgoing statutory auditors', 'REQUIRES_ASSESSMENT'),
  ('xix', 'Material Uncertainty — Going Concern', 'Financial ratios, ageing, and expected cash flows indicating (or not) a material uncertainty', 'LIKELY_APPLICABLE'),
  ('xx', 'CSR Unspent Amount', 'Transfer of unspent CSR amount to the specified fund within the prescribed period', 'REQUIRES_ASSESSMENT'),
  ('xxi', 'Consolidated CARO Qualifications', 'Qualifications or adverse remarks in CARO reports of subsidiaries/associates/JVs included in consolidation', 'REQUIRES_ASSESSMENT');

insert into ifc_control (id, process, control_description, control_type, frequency, automatable) values
  ('P2P-01', 'Procure-to-Pay', 'Vendor master additions and changes are reviewed to prevent duplicate or fictitious vendor records', 'Preventive', 'Transaction', true),
  ('P2P-02', 'Procure-to-Pay', 'Purchase invoices are matched to purchase order and goods receipt before payment (3-way match)', 'Preventive', 'Transaction', false),
  ('O2C-01', 'Order-to-Cash', 'Customer credit limits are reviewed and approved before order fulfilment', 'Preventive', 'Transaction', false),
  ('O2C-02', 'Order-to-Cash', 'Revenue recognized in books is reconciled to GST returns filed for completeness', 'Detective', 'Monthly', true),
  ('R2R-01', 'Record-to-Report', 'Manual journal entries above a defined threshold require independent review and approval', 'Preventive', 'Transaction', false),
  ('R2R-02', 'Record-to-Report', 'Journal entries are monitored for indicators of management override (round amounts, year-end timing, reversals)', 'Detective', 'Monthly', true),
  ('TRE-01', 'Treasury', 'Bank reconciliations are prepared and independently reviewed on a monthly basis', 'Detective', 'Monthly', false),
  ('TRE-02', 'Treasury', 'Trial balance accounts maintain their expected debit/credit nature; anomalies are investigated', 'Detective', 'Monthly', true),
  ('TAX-01', 'Tax Compliance', 'Statutory dues (GST/TDS/PF/ESI) are reconciled between books, challans, and filed returns before payment due dates', 'Detective', 'Monthly', true);
