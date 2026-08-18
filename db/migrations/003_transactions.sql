-- ============================================================
-- 003_transactions.sql
-- Purchase/sales cycle documents, payments/receipts, bank feed.
-- ============================================================

create type doc_direction as enum ('SALES', 'PURCHASE');

create table invoice (
  id             uuid primary key default gen_random_uuid(),
  engagement_id  uuid not null references engagement(id) on delete cascade,
  direction      doc_direction not null,
  invoice_no     text not null,
  invoice_date   date not null,
  vendor_id      uuid references vendor(id),
  customer_id    uuid references customer(id),
  taxable_value  numeric(18,2) not null default 0,
  cgst           numeric(18,2) not null default 0,
  sgst           numeric(18,2) not null default 0,
  igst           numeric(18,2) not null default 0,
  cess           numeric(18,2) not null default 0,
  total_value    numeric(18,2) not null,
  irn            text,                    -- e-invoice IRN, if applicable
  irn_status     text,                    -- ACTIVE / CANCELLED / NOT_APPLICABLE
  eway_bill_no   text,
  check (
    (direction = 'SALES' and customer_id is not null) or
    (direction = 'PURCHASE' and vendor_id is not null)
  )
);
create index idx_invoice_engagement on invoice(engagement_id, direction);
create index idx_invoice_no on invoice(engagement_id, invoice_no);
create index idx_invoice_irn on invoice(irn);

create table credit_debit_note (
  id             uuid primary key default gen_random_uuid(),
  engagement_id  uuid not null references engagement(id) on delete cascade,
  note_type      text not null check (note_type in ('CREDIT_NOTE','DEBIT_NOTE')),
  note_no        text not null,
  note_date      date not null,
  against_invoice_id uuid references invoice(id),
  amount         numeric(18,2) not null,
  reason         text
);
create index idx_note_engagement on credit_debit_note(engagement_id);

create table purchase_order (
  id             uuid primary key default gen_random_uuid(),
  engagement_id  uuid not null references engagement(id) on delete cascade,
  po_no          text not null,
  po_date        date not null,
  vendor_id      uuid references vendor(id),
  amount         numeric(18,2)
);

create table grn (                       -- Goods Receipt Note
  id             uuid primary key default gen_random_uuid(),
  engagement_id  uuid not null references engagement(id) on delete cascade,
  grn_no         text not null,
  grn_date       date not null,
  po_id          uuid references purchase_order(id),
  invoice_id     uuid references invoice(id),
  quantity       numeric(18,4),
  amount         numeric(18,2)
);
create index idx_grn_po on grn(po_id);
create index idx_grn_invoice on grn(invoice_id);

create table payment (
  id             uuid primary key default gen_random_uuid(),
  engagement_id  uuid not null references engagement(id) on delete cascade,
  vendor_id      uuid references vendor(id),
  invoice_id     uuid references invoice(id),
  amount         numeric(18,2) not null,
  payment_date   date not null,
  mode           text,                    -- NEFT/RTGS/Cheque/Cash
  bank_txn_id    uuid                     -- fk added below after bank_transaction is created
);

create table receipt (
  id             uuid primary key default gen_random_uuid(),
  engagement_id  uuid not null references engagement(id) on delete cascade,
  customer_id    uuid references customer(id),
  invoice_id     uuid references invoice(id),
  amount         numeric(18,2) not null,
  receipt_date   date not null,
  mode           text,
  bank_txn_id    uuid
);

create table bank_transaction (
  id             uuid primary key default gen_random_uuid(),
  engagement_id  uuid not null references engagement(id) on delete cascade,
  bank_account_masked text,
  txn_date       date not null,
  description    text,
  amount         numeric(18,2) not null,   -- positive = credit to bank, negative = debit
  balance_after  numeric(18,2),
  match_status   text default 'UNRECONCILED',  -- MATCHED / UNRECONCILED / FLAGGED
  match_reason   text,
  statutory_payment_type text              -- GST / TDS / PF / ESI / PT / INCOME_TAX / null
);
create index idx_bank_txn_engagement_date on bank_transaction(engagement_id, txn_date);
create index idx_bank_txn_status on bank_transaction(engagement_id, match_status);

alter table payment add constraint fk_payment_bank_txn foreign key (bank_txn_id) references bank_transaction(id);
alter table receipt add constraint fk_receipt_bank_txn foreign key (bank_txn_id) references bank_transaction(id);
