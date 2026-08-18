-- ============================================================
-- 022_far_inventory_ingestion.sql
-- fixed_asset and inventory_item tables have existed since
-- migration 005 (Phase 2) but nothing has ever ingested into
-- them — every Data Centre checklist item for these has shown
-- NOT_UPLOADED permanently. This closes that gap.
-- ============================================================

alter type dataset_type add value 'FIXED_ASSET_REGISTER';
alter type dataset_type add value 'INVENTORY_REGISTER';
