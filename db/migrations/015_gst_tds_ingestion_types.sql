-- ============================================================
-- 015_gst_tds_ingestion_types.sql
-- Phase 6 needs GSTR-1/2B/3B and TDS ledger/challan/return as
-- ingestible dataset types, reusing the same upload/validation
-- pipeline built in Phase 4 rather than a parallel one.
-- ============================================================

alter type dataset_type add value 'GSTR1';
alter type dataset_type add value 'GSTR2B';
alter type dataset_type add value 'GSTR3B';
alter type dataset_type add value 'TDS_LEDGER';
alter type dataset_type add value 'TDS_CHALLAN';
alter type dataset_type add value 'TDS_RETURN';
