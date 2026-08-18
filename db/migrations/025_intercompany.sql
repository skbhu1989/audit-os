-- ============================================================
-- 025_intercompany.sql
-- Section 33: Intercompany reconciliation. No prior schema
-- existed for this at all (unlike FAR/Inventory/Loans/Investments,
-- which had tables sitting unused since Phase 2).
--
-- Scoping note: "ENTITY A ↔ ENTITY B" in the spec implies true
-- cross-entity reconciliation, which would need group-structure
-- tracking (which engagement belongs to which group, and access
-- to both entities' books) that this system doesn't have. What's
-- built instead: THIS entity's own intercompany ledger reconciled
-- against an uploaded counterparty confirmation/statement — the
-- same "internal record vs external confirmation" shape as bank
-- reconciliation (Section 54), applied to intercompany balances.
-- Genuine cross-engagement reconciliation is a documented gap,
-- not silently approximated as something it isn't.
-- ============================================================

alter type dataset_type add value 'INTERCOMPANY_LEDGER';
alter type dataset_type add value 'INTERCOMPANY_CONFIRMATION';

create table intercompany_transaction (
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  source          text not null check (source in ('BOOKS','CONFIRMATION')),
  counterparty_name text not null,
  transaction_type text,               -- 'LOAN' / 'RECHARGE' / 'MANAGEMENT_FEE' / 'SHARED_EXPENSE' / 'CROSS_CHARGE' / 'OTHER'
  transaction_date date not null,
  amount          numeric(18,2) not null,   -- positive = counterparty owes us, negative = we owe counterparty
  currency        text default 'INR',        -- informational only; no FX conversion performed (see README)
  reference_no    text,
  ingestion_run_id uuid references ingestion_run(id),
  created_at      timestamptz not null default now()
);
create index idx_intercompany_engagement on intercompany_transaction(engagement_id, source);
create index idx_intercompany_counterparty on intercompany_transaction(counterparty_name);

alter table intercompany_transaction enable row level security;
create policy intercompany_transaction_isolation on intercompany_transaction
  using (fn_engagement_in_current_firm(engagement_id));

grant select, insert, update, delete on intercompany_transaction to app_runtime;
