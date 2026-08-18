-- ============================================================
-- 006_documents_evidence.sql
-- Document storage references, OCR/extraction output, and the
-- Evidence Graph linking any entity to any other (Section CD).
-- ============================================================

create type document_category as enum (
  'INVOICE','CONTRACT','BANK_STATEMENT','LOAN_AGREEMENT','PO','GRN','BOARD_MINUTES',
  'VALUATION_REPORT','LEGAL_OPINION','INSURANCE_DOC','TAX_NOTICE','GST_NOTICE',
  'RETURN_FILING','CHALLAN','CONFIRMATION','OTHER'
);

create table document (
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  category        document_category not null,
  file_name       text not null,
  storage_uri     text not null,           -- s3://... object storage reference; never store blobs in Postgres
  uploaded_by     uuid references app_user(id),
  uploaded_by_client boolean not null default false,  -- true if uploaded via client portal
  uploaded_at     timestamptz not null default now(),
  ocr_status      text default 'PENDING',  -- PENDING / PROCESSING / DONE / FAILED
  version         integer not null default 1,
  supersedes_document_id uuid references document(id)
);
create index idx_document_engagement on document(engagement_id, category);

alter table trial_balance_line add constraint fk_tb_source_file foreign key (source_file_id) references document(id);
alter table compliance_calendar_item add constraint fk_calendar_evidence foreign key (evidence_document_id) references document(id);

create table extracted_field (           -- structured output of OCR/document-AI, one row per field
  id              uuid primary key default gen_random_uuid(),
  document_id     uuid not null references document(id) on delete cascade,
  field_name      text not null,          -- 'party_name' / 'amount' / 'lease_term_months' / 'discount_rate' ...
  field_value     text,
  confidence      numeric(5,4),
  page_number     integer,
  reviewed_by     uuid references app_user(id),
  reviewed_at     timestamptz
);
create index idx_extracted_field_document on extracted_field(document_id);

-- Evidence Graph: a generic typed edge table so any entity (transaction, invoice,
-- ledger entry, procedure, working paper, reviewer) can link to any other,
-- enabling the drill-down/roll-up graph described in Section CD.
create table evidence_edge (
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  from_entity_type text not null,          -- 'journal' / 'invoice' / 'gst_transaction' / 'working_paper' / ...
  from_entity_id  uuid not null,
  to_entity_type  text not null,
  to_entity_id    uuid not null,
  relation        text not null,           -- 'evidenced_by' / 'governed_by' / 'settled_by' / 'signed_off_by' / ...
  created_by      uuid references app_user(id),
  created_at      timestamptz not null default now()
);
create index idx_evidence_edge_from on evidence_edge(from_entity_type, from_entity_id);
create index idx_evidence_edge_to on evidence_edge(to_entity_type, to_entity_id);
create index idx_evidence_edge_engagement on evidence_edge(engagement_id);
