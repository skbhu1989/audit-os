-- ============================================================
-- 001_tenancy.sql
-- Firms, users, clients, engagements, periods.
-- Every downstream table traces back to firm_id (via client/engagement)
-- for row-level tenant isolation (see 010_audit_trail_and_rls.sql).
-- ============================================================

create extension if not exists "pgcrypto";   -- gen_random_uuid()
create extension if not exists "citext";     -- case-insensitive email/PAN/GSTIN matching

create type user_role as enum (
  'FIRM_ADMIN', 'PARTNER', 'MANAGER', 'SENIOR', 'ARTICLE',
  'EQCR_REVIEWER', 'CLIENT_USER', 'SYSTEM_INTEGRATION'
);

create table firm (
  id            uuid primary key default gen_random_uuid(),
  name          text not null,
  icai_frn      text,                       -- Firm Registration Number
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create table app_user (
  id            uuid primary key default gen_random_uuid(),
  firm_id       uuid not null references firm(id) on delete cascade,
  email         citext not null unique,
  full_name     text not null,
  role          user_role not null,
  mfa_enabled   boolean not null default false,
  is_active     boolean not null default true,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index idx_app_user_firm on app_user(firm_id);

create type accounting_framework as enum ('IND_AS', 'AS', 'IFRS', 'OTHER');
create type listing_status as enum ('LISTED', 'UNLISTED', 'NBFC', 'BANKING', 'INSURANCE', 'OTHER_REGULATED');

create table client (
  id                uuid primary key default gen_random_uuid(),
  firm_id           uuid not null references firm(id) on delete cascade,
  legal_name        text not null,
  cin               text,
  pan               citext,
  tan               citext,
  gstin_primary     citext,
  industry          text,
  listing_status    listing_status not null default 'UNLISTED',
  framework         accounting_framework,      -- may be null until Framework Engine determines it
  group_parent_id   uuid references client(id),-- for subsidiary/associate/JV linkage
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
create index idx_client_firm on client(firm_id);
create index idx_client_pan on client(pan);
create index idx_client_gstin on client(gstin_primary);

create table client_gstin (            -- clients can hold multiple GSTINs (multi-state)
  id            uuid primary key default gen_random_uuid(),
  client_id     uuid not null references client(id) on delete cascade,
  gstin         citext not null,
  state         text,
  status        text default 'ACTIVE',   -- ACTIVE / CANCELLED / SUSPENDED (per master-data consistency engine)
  unique (client_id, gstin)
);

create type engagement_status as enum (
  'ONBOARDING', 'DATA_COLLECTION', 'FIELDWORK', 'REVIEW', 'REPORTING', 'CLOSED'
);

create table engagement (
  id                        uuid primary key default gen_random_uuid(),
  client_id                 uuid not null references client(id) on delete cascade,
  financial_year            text not null,          -- e.g. '2025-26'
  reporting_date            date not null,
  framework                 accounting_framework not null,
  overall_materiality       numeric(18,2),
  performance_materiality   numeric(18,2),
  clearly_trivial_threshold numeric(18,2),
  materiality_benchmark     text,                    -- 'PBT' | 'REVENUE' | 'TOTAL_ASSETS' | ...
  status                    engagement_status not null default 'ONBOARDING',
  engagement_partner_id     uuid references app_user(id),
  engagement_manager_id     uuid references app_user(id),
  created_at                timestamptz not null default now(),
  updated_at                timestamptz not null default now(),
  unique (client_id, financial_year)
);
create index idx_engagement_client on engagement(client_id);
create index idx_engagement_status on engagement(status);

create table period (                   -- monthly/quarterly sub-periods within an engagement
  id            uuid primary key default gen_random_uuid(),
  engagement_id uuid not null references engagement(id) on delete cascade,
  label         text not null,           -- 'Apr-2025' ... 'Mar-2026'
  start_date    date not null,
  end_date      date not null,
  close_status  text default 'OPEN',     -- OPEN / GREEN / AMBER / RED / CLOSED (month-end close engine)
  unique (engagement_id, label)
);
create index idx_period_engagement on period(engagement_id);

create table engagement_team (           -- role assignment per engagement (distinct from firm-wide role)
  engagement_id uuid not null references engagement(id) on delete cascade,
  user_id       uuid not null references app_user(id) on delete cascade,
  engagement_role text not null,         -- may differ from app_user.role, e.g. a Manager acting as EQCR
  primary key (engagement_id, user_id)
);
