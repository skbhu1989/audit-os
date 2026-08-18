-- ============================================================
-- 020_upload_dedup.sql
-- Section 41: detect re-uploads of the same file rather than
-- silently double-ingesting. Found the need for this the hard way —
-- testing Phase-2's Pre-Audit module re-uploaded 17 sample files to
-- populate coverage data and silently duplicated every row in the
-- Meridian Fashions test engagement, corrupting bank reconciliation
-- and challan mapping results until traced back to this root cause.
-- ============================================================

alter table ingestion_run add column content_hash text;
create index idx_ingestion_run_hash on ingestion_run(engagement_id, dataset_type, content_hash);
