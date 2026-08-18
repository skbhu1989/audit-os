-- ============================================================
-- 005_assets_capital.sql
-- Fixed Asset Register, inventory, loans, investments,
-- share capital, related parties.
-- ============================================================

create table fixed_asset (
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  asset_code      text,
  description     text not null,
  category        text,                    -- Plant & Machinery, Furniture, Vehicles, ...
  acquisition_date date,
  gross_block     numeric(18,2) not null default 0,
  accum_depreciation numeric(18,2) not null default 0,
  net_block       numeric(18,2) generated always as (gross_block - accum_depreciation) stored,
  useful_life_years numeric(6,2),
  depreciation_method text,                -- SLM / WDV
  disposal_date   date,
  disposal_proceeds numeric(18,2),
  is_cwip         boolean not null default false,
  impairment_indicator boolean not null default false,
  physically_verified boolean not null default false
);
create index idx_fixed_asset_engagement on fixed_asset(engagement_id);

create table inventory_item (
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  item_code       text,
  description     text not null,
  quantity_on_hand numeric(18,4) not null default 0,
  unit_cost       numeric(18,4),
  nrv             numeric(18,4),           -- Net Realisable Value
  ageing_days     integer,
  is_slow_moving  boolean not null default false,
  is_obsolete     boolean not null default false
);
create index idx_inventory_engagement on inventory_item(engagement_id);

create table loan (
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  lender_or_borrower text not null,        -- e.g. 'HDFC Bank' or a related_party name
  direction       text not null check (direction in ('BORROWING','LENDING')),
  principal_amount numeric(18,2) not null,
  interest_rate   numeric(6,3),
  start_date      date,
  maturity_date   date,
  outstanding_balance numeric(18,2),
  is_related_party boolean not null default false,
  security_details text,
  roc_charge_id   text                     -- MCA charge reference for reconciliation
);
create index idx_loan_engagement on loan(engagement_id);

create table investment (
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  investee_name   text not null,
  investment_type text,                    -- Equity / Preference / CCD / CCPS / Mutual Fund / ...
  classification  text,                    -- FVTPL / FVOCI / Amortised Cost (Ind AS 109)
  cost            numeric(18,2),
  fair_value      numeric(18,2),
  fair_value_date date,
  is_subsidiary_associate_jv text          -- SUBSIDIARY / ASSOCIATE / JV / OTHER / null
);
create index idx_investment_engagement on investment(engagement_id);

create table share_capital_entry (
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  event_type      text not null,           -- ALLOTMENT / TRANSFER / BUYBACK / SPLIT
  event_date      date not null,
  shareholder_name text,
  number_of_shares numeric(18,2),
  face_value      numeric(18,4),
  premium         numeric(18,4),
  mca_filing_ref  text                     -- for MCA/ROC reconciliation
);
create index idx_share_capital_engagement on share_capital_entry(engagement_id);

create table related_party (
  id              uuid primary key default gen_random_uuid(),
  engagement_id   uuid not null references engagement(id) on delete cascade,
  name            text not null,
  relationship    text,                    -- Director / KMP / Subsidiary / Common director / ...
  identified_via  text[],                  -- ['common_director','common_address','vendor_link', ...]
  pan             citext,
  vendor_id       uuid references vendor(id),
  customer_id     uuid references customer(id),
  confidence      text default 'SYSTEM_IDENTIFIED'  -- SYSTEM_IDENTIFIED / CONFIRMED / REJECTED
);
create index idx_related_party_engagement on related_party(engagement_id);
