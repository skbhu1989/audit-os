-- ============================================================
-- 023_far_inventory_ingestion_run_id.sql
-- fixed_asset and inventory_item predate the ingestion_run_id
-- pattern (added later, migrations 013/017, for trial_balance_line/
-- journal/vendor/customer/payroll_line). Adding it here too so
-- REPLACE-on-duplicate-upload works consistently for these tables.
-- ============================================================

alter table fixed_asset add column ingestion_run_id uuid references ingestion_run(id);
alter table inventory_item add column ingestion_run_id uuid references ingestion_run(id);
