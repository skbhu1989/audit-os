-- ============================================================
-- 024_loans_investments_ingestion.sql
-- loan and investment tables have existed since migration 005
-- (Phase 2) with no ingestion path — closing that gap, same
-- pattern as FAR/Inventory in migration 022.
-- ============================================================

alter type dataset_type add value 'LOAN_REGISTER';
alter type dataset_type add value 'INVESTMENT_REGISTER';

alter table loan add column ingestion_run_id uuid references ingestion_run(id);
alter table investment add column ingestion_run_id uuid references ingestion_run(id);
