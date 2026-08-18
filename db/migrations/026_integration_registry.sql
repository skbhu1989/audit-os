-- ============================================================
-- 026_integration_registry.sql
-- Section 44 is explicit and repeated: NEVER fake a live
-- connection to GST/Income Tax/MCA/Banks/TDS/Tally/other
-- government or third-party systems. This table is the honest
-- record of what's actually connected (nothing, in this build)
-- vs what's available as a file-upload fallback (everything that
-- matters, per the ingestion pipeline built across prior phases).
-- ============================================================

create type integration_classification as enum (
  'FREE', 'FREE_WITH_LIMITS', 'GOVERNMENT_AUTHENTICATED', 'THIRD_PARTY_PAID', 'OPTIONAL', 'NOT_PUBLICLY_AVAILABLE'
);
create type integration_status as enum ('NOT_CONNECTED', 'CONNECTED', 'DEGRADED', 'DOWN');

create table integration_provider (
  id                  text primary key,        -- 'GST_LIVE', 'TALLY_LOCAL', etc.
  display_name        text not null,
  category            text not null,           -- 'GST' / 'TDS' / 'INCOME_TAX' / 'MCA' / 'BANKING' / 'ACCOUNTING_SOFTWARE' / 'OCR'
  classification      integration_classification not null,
  classification_reason text not null,         -- why it's classified this way — never claim FREE without justification (Section 2)
  status              integration_status not null default 'NOT_CONNECTED',
  auth_type           text,                    -- 'OAUTH2' / 'API_KEY' / 'GSP_ASP_REGISTRATION' / 'LOCAL_NETWORK' / null
  fallback_available  boolean not null default true,
  fallback_description text,
  last_successful_sync timestamptz,
  last_failed_sync    timestamptz,
  last_error          text
);

grant select, insert, update, delete on integration_provider to app_runtime;

-- ---------- Seed data: honest classification of every integration named in
-- the spec, based on actual publicly known access models as of this
-- system's knowledge — not verified against live current terms, so treated
-- as a starting reference an implementer should confirm before relying on. ----------

insert into integration_provider (id, display_name, category, classification, classification_reason, auth_type, fallback_available, fallback_description) values
  ('GST_LIVE', 'GST Portal (GSTN)', 'GST', 'NOT_PUBLICLY_AVAILABLE',
   'GSTN does not offer free, direct public API access to taxpayer return/ledger data — access requires GSP/ASP (GST Suvidha Provider) registration, which is a paid, licensed intermediary arrangement, not a free public API.',
   'GSP_ASP_REGISTRATION', true, 'Upload GSTR-1/GSTR-2B/GSTR-3B files exported from the GST portal (already supported: GSTR1/GSTR2B/GSTR3B dataset types).'),

  ('TDS_TRACES', 'TRACES (TDS Portal)', 'TDS', 'GOVERNMENT_AUTHENTICATED',
   'TRACES requires a registered deductor login; no public API is offered for third-party applications to pull Form 26AS/16/16A data programmatically.',
   'LOCAL_NETWORK', true, 'Upload TDS ledger, challan, and return files exported from TRACES (already supported: TDS_LEDGER/TDS_CHALLAN/TDS_RETURN dataset types).'),

  ('INCOME_TAX_PORTAL', 'Income Tax e-Filing / AIS', 'INCOME_TAX', 'GOVERNMENT_AUTHENTICATED',
   'AIS/TIS/26AS are accessible only via authenticated taxpayer login on the e-filing portal; no public API exists for third-party pull access.',
   null, true, 'Upload downloaded AIS/26AS/ITR statements manually (not yet built as a structured ingestion type — see Known Gaps).'),

  ('MCA_PORTAL', 'MCA21 / MCA Portal', 'MCA', 'GOVERNMENT_AUTHENTICATED',
   'MCA does not offer a free public API for company filings, charges, or director data; access is via the authenticated MCA21 portal or paid data resellers.',
   null, true, 'Upload MCA-downloaded documents/PDFs manually (not yet built as a structured ingestion type — see Known Gaps).'),

  ('BANK_OPEN_BANKING', 'Bank / Account Aggregator', 'BANKING', 'THIRD_PARTY_PAID',
   'India''s Account Aggregator framework requires licensing as an AA-registered FIU and typically involves per-transaction or subscription fees from AA/TSP providers — not free for a third-party application to integrate directly.',
   'OAUTH2', true, 'Upload bank statement exports (CSV/Excel) — already supported and load-bearing throughout this system (BANK_STATEMENT dataset type).'),

  ('TALLY_LOCAL', 'Tally / TallyPrime', 'ACCOUNTING_SOFTWARE', 'FREE',
   'Tally exposes a local XML-over-HTTP interface at no additional cost when Tally is installed and configured to allow ODBC/HTTP access on the same network as this application — genuinely free, but requires the user''s own Tally instance to be reachable, which cannot be verified or connected from this sandboxed environment.',
   'LOCAL_NETWORK', true, 'Export Tally data to Excel/CSV and upload via the standard file ingestion pipeline (Trial Balance, General Ledger, Sales/Purchase Register all already supported this way).'),

  ('ZOHO_BOOKS', 'Zoho Books', 'ACCOUNTING_SOFTWARE', 'FREE_WITH_LIMITS',
   'Zoho Books offers an official OAuth2 API with a free tier subject to rate limits; using it requires registering an OAuth application with Zoho and obtaining client credentials, which this environment does not have.',
   'OAUTH2', true, 'Export data from Zoho Books to Excel/CSV and upload via the standard file ingestion pipeline.'),

  ('OCR_PROVIDER', 'Document OCR / Extraction', 'OCR', 'OPTIONAL',
   'Cloud OCR providers (Textract, Document AI, etc.) are typically paid or free-tier-limited; a fully free local option (e.g. Tesseract) exists but is not wired into this build — Document Intelligence (Section 63/Section 20-21 of this instruction) is not implemented in this phase.',
   'API_KEY', false, 'No fallback yet — document field extraction is not built; only structured tabular file upload is supported.');
