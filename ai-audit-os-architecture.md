# AI-Powered Indian Financial Audit Operating System
### Phase 1 — Product & Architecture Specification

---

## 1. Product Requirements Document (PRD)

**Product**: An AI Audit Operating System for Indian Chartered Accountants — a data-first, rule-driven, evidence-backed platform that automates the mechanical parts of a statutory financial audit (data reconciliation, analytics, risk scoring, working-paper drafting) while leaving all conclusions, judgement and sign-off to a human auditor.

**Primary users**: Audit partners, managers, seniors, article assistants, quality reviewers, and (read/upload-only) client finance teams.

**Core value proposition**: Replace Excel-based reconciliation and sampling with a connected data model that ties books → statutory returns → challans → government records → financial statements, so that every audit finding is explainable and traceable to source.

**Primary workflow** (see Section CA of the master prompt): Client → Engagement → FY/Framework → Data Upload → Validation → TB Mapping → Materiality → Analytics → Risk → Exceptions → Procedures → PBC → Evidence → Testing → Working Papers → Review → Close.

**Non-goals for V1**: Issuing audit opinions, auto-filing returns, replacing auditor judgement, real-time government API integration (built as a pluggable adapter, not a V1 dependency).

**Success metrics**: % of TB lines auto-mapped and accepted, % of JE population risk-scored, GST/TDS reconciliation cycle time reduction, number of working papers auto-drafted vs. manually written, audit readiness score accuracy vs. actual closure blockers.

---

## 2. System Architecture

```
                        ┌───────────────────────────┐
                        │      WEB CLIENT (SPA)      │
                        │  Auditor Dashboard / Portal│
                        └─────────────┬─────────────┘
                                      │ HTTPS/GraphQL+REST
                        ┌─────────────▼─────────────┐
                        │        API GATEWAY         │
                        │  Auth · Rate limit · RBAC   │
                        └──┬───────┬───────┬─────────┘
             ┌─────────────┘       │       └──────────────┐
   ┌─────────▼─────────┐ ┌─────────▼─────────┐ ┌───────────▼──────────┐
   │  CORE AUDIT API    │ │  ANALYTICS/RULE    │ │   AI / RAG SERVICE    │
   │ (clients, TB, WP,  │ │  ENGINE (async     │ │ (LLM orchestration,   │
   │  queries, evidence)│ │  workers, queue)    │ │  embeddings, OCR)     │
   └─────────┬─────────┘ └─────────┬─────────┘ └───────────┬──────────┘
             │                     │                        │
   ┌─────────▼─────────────────────▼────────────────────────▼──────────┐
   │                        DATA LAYER                                  │
   │  Postgres (transactional) │ Object Storage (docs) │ Vector DB (RAG) │
   │  Redis (cache/queue)      │ Data warehouse (analytics, optional)   │
   └──────────────────────────────────────────────────────────────────┘
```

Design principle (per Section B of the master prompt): the LLM sits in the AI/RAG service only. GST/TDS math, materiality, sampling, and reconciliation matching run in the deterministic Analytics/Rule Engine — the LLM interprets and explains results, it does not compute them.

---

## 3. Module Architecture

| Module | Responsibility |
|---|---|
| Identity & Tenancy | Firms, users, roles, client-level data isolation |
| Client & Engagement | Onboarding, framework applicability, materiality |
| Data Ingestion | Excel/CSV/Tally parsers → Universal Data Model |
| Data Validation | Data quality score, exception report |
| Trial Balance & Mapping | Ledger → FS line → note mapping |
| GL Analytics & JE Testing | Trend/ratio analysis, risk-scored journals |
| AP / AR / Bank / FA / Inventory / Payroll | Sub-ledger specific testing |
| Statutory Reconciliation | GST, TDS, PF/ESI, Income Tax, MCA reconciliation sub-engines |
| Matching Engine | Shared L1–L6 matching service used by all reconciliations |
| Risk Engine | Converts exceptions into scored, categorised audit risk |
| Sampling Engine | Random / MUS / stratified / risk-based sampling |
| Evidence & Document AI | Upload, OCR, extraction, evidence graph |
| Working Papers | Auto-draft, versioning, sign-off |
| PBC / Query Management | Auto-generated requests, client portal, status tracking |
| CARO / IFC Engine | Clause/process-level assisted drafting |
| AI Assistant | NL query orchestration over the above modules |
| Reporting | Exports (Excel/PDF/Word), dashboards |
| Audit Trail & Security | Versioning, logging, RBAC, encryption |

---

## 4. Database Architecture

- **Relational (PostgreSQL, primary system of record)**: clients, engagements, ledgers, journals, sub-ledger masters, reconciliation results, exceptions, working papers, users/roles, audit trail. Chosen for strong consistency, referential integrity across a highly relational audit data model, and mature partitioning for scale.
- **Object storage (S3-compatible)**: uploaded source files, evidence documents, generated PDFs/Excel exports. Referenced by URI from Postgres, never stored as blobs in the DB.
- **Vector database (pgvector or a dedicated store)**: embeddings of Ind AS/AS/IFRS/SA/Companies Act/GST/Income Tax corpus for the RAG engine, plus embeddings of client contracts/documents for semantic search.
- **Cache/Queue (Redis)**: session cache, rate limiting, and the job queue backing the async Analytics/Rule Engine (large-file reconciliation, journal testing) so the UI is never blocked.
- **Optional analytical store (columnar warehouse, e.g. ClickHouse/BigQuery)**: only introduced once a tenant's transaction volume moves into the 10M+ range (see Section 21, Scalability) — keeps the OLTP Postgres instance lean.

Multi-tenancy: every table carries `firm_id` and `client_id`; row-level security policies enforce isolation at the database layer, not just in application code.

---

## 5. Entity Relationship Model (core entities)

```
Firm 1──* User
Firm 1──* Client 1──* Engagement 1──* Period
Engagement 1──* Ledger 1──* Journal 1──* JournalLine ──* Account
Engagement 1──* Vendor / Customer / Employee
Engagement 1──* Invoice / CreditNote / DebitNote / PO / GRN
Engagement 1──* BankTransaction
Engagement 1──* GSTTransaction / TDSTransaction / Challan / Return
Engagement 1──* StatutoryLiability 1──* LiabilityRollForward
Engagement 1──* FixedAsset / InventoryItem / Loan / Investment / ShareCapitalEntry
Engagement 1──* RelatedParty
Engagement 1──* Document ──* ExtractedField
Engagement 1──* AuditProcedure 1──* AuditEvidence
Engagement 1──* AuditException ──* AuditQuery
Engagement 1──* WorkingPaper (references Procedure, Evidence, Exception)
Engagement 1──* ReconciliationRun ──* ReconciliationMatch / ReconciliationException
Every mutable record ──* AuditTrailEvent (append-only)
```

Key cross-cutting relationship: `AuditException` is the hub — every reconciliation, JE test, and analytics flag ultimately produces (or updates) an `AuditException`, which is what drives Queries, Working Papers, and the Risk Engine.

---

## 6. Data Flow

```
FILE UPLOAD → PARSER (format-specific) → UNIVERSAL DATA MODEL (staging)
   → VALIDATION ENGINE → DATA QUALITY SCORE
   → NORMALIZATION (party/ledger/GSTIN/PAN de-dup) → COMMITTED DATA MODEL
   → TB MAPPING (AI-assisted, human-approved)
   → RULE ENGINE (materiality, GST/TDS calc, thresholds)
   → RECONCILIATION ENGINE (matching hierarchy L1–L6)
   → EXCEPTION ENGINE → RISK ENGINE (scored, categorised)
   → AI LAYER (interprets exceptions, drafts queries/WP narrative, cites RAG sources)
   → HUMAN REVIEW (accept/reject/modify, mandatory for sign-off)
   → WORKING PAPER (versioned) → AUDIT FILE
```

---

## 7. AI / RAG Architecture

- **Orchestration layer**: routes a user/system request to the right tool — rule engine call, SQL analytics query, or RAG lookup — and composes the final explainable answer. The LLM never computes GST/TDS/materiality numbers itself; it calls the deterministic engines and narrates the result.
- **Knowledge corpus** (chunked, versioned, source-tagged): Ind AS, AS, IFRS/IAS, Companies Act + Schedule III, ICAI SAs, CARO, Income Tax Act/Rules, GST Act/Rules, circulars/notifications. Each chunk stores: source type (Statute/Rule/Standard/Circular/Guidance/Commentary), effective date, expiry/superseding reference.
- **Retrieval**: embed query → vector search restricted to chunks valid as of the engagement's reporting date (see Section 9, Date/Version Engine) → re-rank → pass top-k with citations into the LLM context.
- **Citation enforcement**: every technical statement in an AI answer must carry a source chunk ID; the orchestration layer rejects/flags any LLM output that makes a technical claim without a matching citation.
- **OCR/document intelligence**: separate pipeline (layout-aware OCR → field extraction → structured JSON) feeding the Evidence Graph; LLM only interprets already-extracted structured fields, reducing hallucination surface on numbers.

---

## 8. Rule Engine Architecture

- Rules are stored as **versioned, effective-dated rows** in a `rule` / `rule_version` table (see Section 20 schema), not hardcoded in application or UI code.
- Each rule version has: `rule_code`, `category` (GST/TDS/Companies Act/Materiality/…), `logic` (structured expression or reference to a rule-evaluation function), `effective_from`, `effective_to`, `source_reference`.
- A **rule evaluator service** takes `(rule_code, transaction_context, as_of_date)` and returns the applicable rule version's result — never "current" logic applied blindly to a historical period.
- Examples of rule categories: TDS section/threshold/rate tables, GST rate/HSN tables, materiality benchmark formulas, statutory due-date calendars, depreciation rate tables (Companies Act Schedule II / Income Tax).
- Rule changes never overwrite history — a new `rule_version` row is inserted; old versions remain queryable for prior-period audits (Section BU).

---

## 9. Audit Engine Architecture

- **Procedure library**: catalogued `AuditProcedure` templates, each tagged with the FS assertion(s) it addresses (Existence, Completeness, Accuracy, Valuation, Rights & Obligations, Cut-off, Classification, Presentation, Disclosure) and the relevant SA.
- **Trigger model**: an `AuditException` (from reconciliation, JE testing, or analytics) is mapped via a rules table to one or more suggested `AuditProcedure`s — this mapping is itself a versioned rule set, not LLM-generated on the fly, though the LLM drafts the narrative around it.
- **Evidence linkage**: every procedure instance records population, sample, evidence documents obtained/missing, and conclusion — structured exactly per the Working Paper schema (Section 24).
- **Sign-off state machine**: Draft → Prepared → Reviewed → Approved, with reviewer/approver identity and timestamp immutable once set (new corrections create a new version, not an edit).

---

## 10. Reconciliation Engine Architecture

Single shared service used by GST, TDS, PF/ESI, Income Tax, MCA, and bank reconciliation modules — implementing the matching hierarchy from Section AZ:

```
INPUT: sourceDataset A, sourceDataset B, matchConfig
  L1  exact unique identifier (e.g. CPIN, IRN, challan no.)
  L2  document number + GSTIN/PAN
  L3  amount + date + party
  L4  amount + party + period
  L5  fuzzy match (name similarity, tolerance bands on amount/date)
  L6  AI-assisted match (embedding similarity + LLM disambiguation)
OUTPUT: for each row → { status: MATCHED | PARTIAL | UNMATCHED,
                          matchLevel, confidence, matchingFactors[],
                          sourceRecordA, sourceRecordB, difference }
```

Every match produced above L2 is written as a `ReconciliationMatch` with `confidence_score` and `matching_factors[]`, and stays in an "AI-suggested" state until an auditor calls Accept / Reject / Modify / Merge / Split — each action logged to the audit trail (Section 92).

---

## 11. Security Architecture

- **AuthN**: SSO + MFA (TOTP/WebAuthn) at the firm level.
- **AuthZ**: RBAC (Section 12/13) enforced at API layer and reinforced with Postgres row-level security keyed on `firm_id`/`client_id`.
- **Encryption**: TLS in transit; AES-256 at rest for DB and object storage; client-specific encryption keys (envelope encryption) for the most sensitive document classes (tax notices, bank statements).
- **Isolation**: hard tenant isolation — no cross-client query paths in the application layer; document-level permissions on top of engagement-level access.
- **Audit logging**: every read/write of financial data logged (who, when, what, from where) to an append-only log store, separate from the transactional DB.
- **Data governance**: explicit contractual opt-in required before any client data is used to fine-tune or improve any model; default is strictly no external training use (Section BY).
- **Retention & deletion**: configurable per-engagement retention policy aligned to ICAI/Companies Act document retention requirements; secure (crypto-shred) deletion on expiry.

---

## 12. User Roles

| Role | Description |
|---|---|
| Firm Admin | Manages firm settings, users, billing, security policy |
| Engagement Partner | Full access to assigned engagements; final approver |
| Manager | Reviews working papers, approves procedures, manages team |
| Senior / Article Assistant | Prepares working papers, runs reconciliations, drafts queries |
| Quality Reviewer (EQCR) | Independent review access, read + comment |
| Client User (Portal) | Upload documents, respond to queries, view PBC list only |
| System/Integration Account | Scoped API access for data connectors |

---

## 13. Permission Model

A role × module × action matrix (illustrative):

| Module | Article/Senior | Manager | Partner | EQCR | Client |
|---|---|---|---|---|---|
| Data upload | Create | Create/Edit | Create/Edit | View | Create (own docs only) |
| TB mapping | Propose | Approve | Approve | View | — |
| Reconciliation actions (Accept/Reject/Modify) | Propose | Approve | Approve | View | — |
| Working papers | Draft | Review | Approve/Sign-off | Comment | — |
| CARO/IFC conclusions | Draft | Review | Approve | Comment | — |
| Audit report | View | View | Sign | View | — |
| Client queries | Draft | Send | Send | View | Respond |
| User management | — | — | Firm Admin only | — | — |

Every state-changing action is permission-checked server-side regardless of UI role gating.

---

## 14. MVP Scope

Per Section BZ — Version 1 covers: Auth, Client/Engagement management, Excel/CSV/Tally ingestion, Data validation, TB mapping, GL analytics, JE testing, AP/AR analytics, Bank reconciliation, GST reconciliation, TDS reconciliation, Duplicate detection, Risk engine, Audit queries, Evidence management, Working papers, Audit dashboard.

MVP inputs: Trial Balance, General Ledger, Sales Register, Purchase Register, Bank Statement, Vendor Master, Customer Master.

---

## 15. Phase-wise Development Roadmap

| Phase | Scope | Indicative duration |
|---|---|---|
| 1 | Architecture & spec (this document) | done |
| 2 | Database schema, universal data model | 2–3 weeks |
| 3 | Auth, tenancy, client/engagement management | 2 weeks |
| 4 | Data upload, parsers, validation engine | 3 weeks |
| 5 | TB mapping + GL engine | 3 weeks |
| 6 | GL/JE analytics | 3 weeks |
| 7 | Risk engine + materiality | 2 weeks |
| 8 | GST + TDS reconciliation engines | 4–5 weeks |
| 9 | Evidence management + working papers | 3 weeks |
| 10 | AI assistant (RAG + orchestration) | 3–4 weeks |
| 11 | Payroll/MCA/Income Tax reconciliation, PBC portal | 4 weeks |
| 12 | CARO, IFC, financial statement review, reporting suite | 5–6 weeks |

(Estimates assume a small dedicated team; sequencing matters more than exact durations.)

---

## 16. API Architecture

- **Style**: REST for CRUD-style resources (clients, engagements, documents); a small GraphQL surface for the dashboard's aggregate/drill-down queries (avoids over/under-fetching across deeply nested reconciliation data).
- **Async pattern**: long-running jobs (large-file reconciliation, JE testing, OCR) submitted via `POST /jobs`, return a `job_id`, status polled via `GET /jobs/{id}` or pushed via WebSocket/SSE — UI never blocks on synchronous processing of large files.
- **Illustrative endpoints**:
  - `POST /clients`, `POST /clients/{id}/engagements`
  - `POST /engagements/{id}/data/upload`, `GET /engagements/{id}/data/validation-report`
  - `POST /engagements/{id}/tb/map`, `GET /engagements/{id}/tb`
  - `POST /engagements/{id}/reconciliations/gst/run`, `GET /engagements/{id}/reconciliations/gst/exceptions`
  - `POST /reconciliations/{id}/matches/{matchId}/accept|reject|modify|merge|split`
  - `GET /engagements/{id}/risk-summary`
  - `POST /engagements/{id}/working-papers`, `PATCH /working-papers/{id}/sign-off`
  - `POST /ai/ask` `{ question, engagementId }` → structured `{ answer, dataUsed, calculation, standard, evidence, implication, procedure }`
- **Versioning**: `/v1/...` namespace; breaking changes ship as `/v2` with a deprecation window.

---

## 17. Recommended Technology Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React (Next.js), TypeScript, Tailwind | Fast iteration, strong ecosystem for data-heavy dashboards |
| Backend API | Node.js (NestJS) or Python (FastAPI) | Both fine; FastAPI eases sharing code with the Python analytics layer |
| Analytics/Rule Engine | Python (pandas/polars, NumPy) run as async workers | Needed for large-scale GL/JE analytics, sampling, Benford's Law |
| Job Queue | Celery/RQ (Python) or BullMQ (Node) on Redis | Async processing without blocking UI |
| Relational DB | PostgreSQL | ACID, row-level security, strong relational modelling fit |
| Object Storage | S3-compatible | Documents/evidence, cheap and durable |
| Vector Store | pgvector (start), dedicated (Weaviate/Pinecone) at scale | RAG over regulatory corpus and documents |
| OCR/Doc AI | Managed OCR (e.g. Textract/Document AI) + custom extraction layer | Avoid building OCR from scratch |
| LLM | Claude via API, called only from the AI/RAG service | Central orchestration, never embedded ad hoc in UI |
| Auth | OAuth2/OIDC + WebAuthn for MFA | Standard, auditable |
| Infra | Containerized (Docker/Kubernetes), managed cloud (AWS/GCP/Azure, India region for data residency) | Scalability, compliance |

---

## 18. Folder Structure (monorepo)

```
audit-os/
├── apps/
│   ├── web/                # Next.js frontend
│   ├── api/                # Core Audit API (NestJS/FastAPI)
│   ├── analytics-worker/   # Python rule/analytics engine (async jobs)
│   └── ai-service/         # RAG orchestration + LLM calls
├── packages/
│   ├── data-model/         # Shared Universal Data Model types/schemas
│   ├── rule-engine/        # Versioned rule evaluation library
│   ├── reconciliation-engine/ # Shared matching hierarchy L1–L6
│   └── ui-components/      # Shared design system
├── infra/
│   ├── db/migrations/
│   ├── k8s/
│   └── terraform/
└── docs/
    └── architecture/       # This document and future ADRs
```

---

## 19. UI Screen Map

```
/dashboard
/clients, /clients/:id
/engagements/:id
  /data                (upload, validation report)
  /trial-balance
  /general-ledger      (JE testing)
  /risk
  /procedures
  /working-papers
  /ap  /ar  /revenue  /bank  /inventory  /fixed-assets
  /tax  /gst  /tds  /payroll
  /related-parties
  /fraud-analytics
  /statutory-reconciliation   (Universal Reconciliation Matrix, Section CC)
  /caro  /ifc
  /financial-statements
  /pbc  /queries  /evidence
  /review
  /audit-report
/ai-assistant (available as a persistent side panel across all screens)
```

---

## 20. Sample Database Schema (illustrative DDL)

```sql
create table firm (id uuid primary key, name text, created_at timestamptz default now());

create table app_user (
  id uuid primary key, firm_id uuid references firm(id),
  email text unique, role text, mfa_enabled boolean default false
);

create table client (
  id uuid primary key, firm_id uuid references firm(id),
  legal_name text, cin text, pan text, tan text,
  listing_status text, framework text check (framework in ('IND_AS','AS','IFRS','OTHER'))
);

create table engagement (
  id uuid primary key, client_id uuid references client(id),
  financial_year text, reporting_date date,
  overall_materiality numeric, performance_materiality numeric,
  status text default 'IN_PROGRESS'
);

create table ledger_entry (          -- Trial Balance line
  id uuid primary key, engagement_id uuid references engagement(id),
  ledger_name text, account_head text, fs_line text,
  debit numeric default 0, credit numeric default 0,
  flag text, mapped_by uuid, mapped_at timestamptz
);

create table journal (
  id uuid primary key, engagement_id uuid references engagement(id),
  journal_no text, posted_date date, posted_by text, narration text,
  amount numeric, risk_score numeric, risk_level text,
  risk_reasons text[]
);

create table rule (
  code text primary key, category text, description text
);
create table rule_version (
  id uuid primary key, rule_code text references rule(code),
  logic jsonb, effective_from date, effective_to date,
  source_reference text
);

create table reconciliation_run (
  id uuid primary key, engagement_id uuid references engagement(id),
  recon_type text,        -- e.g. 'GST_BOOKS_VS_GSTR1'
  period text, run_at timestamptz default now(), run_by uuid
);
create table reconciliation_exception (
  id uuid primary key, run_id uuid references reconciliation_run(id),
  gstin text, document_no text, document_date date, party text,
  taxable_value numeric, cgst numeric, sgst numeric, igst numeric, cess numeric,
  books_amount numeric, return_amount numeric, difference numeric,
  reason text, risk_level text, suggested_action text,
  status text default 'OPEN'          -- Open/Under Review/Query Raised/... /Closed
);

create table working_paper (
  id uuid primary key, engagement_id uuid references engagement(id),
  objective text, assertion text[], applicable_standard text,
  population text, sample jsonb, procedure text, evidence_refs uuid[],
  exceptions uuid[], conclusion text,
  preparer_id uuid, reviewer_id uuid, approver_id uuid,
  status text default 'DRAFT', version int default 1
);

create table audit_trail_event (
  id bigserial primary key, engagement_id uuid, entity_table text, entity_id uuid,
  action text, actor_id uuid, occurred_at timestamptz default now(), diff jsonb
);
```

---

## 21. Sample GST Reconciliation Logic (pseudocode)

```python
def reconcile_gstr1_vs_gstr3b(period, engagement_id):
    gstr1 = load_return("GSTR1", engagement_id, period)   # invoice-level
    gstr3b = load_return("GSTR3B", engagement_id, period) # summary-level

    gstr1_summary = gstr1.groupby("tax_head").sum("taxable_value")
    diffs = []
    for tax_head, gstr1_amt in gstr1_summary.items():
        gstr3b_amt = gstr3b.get(tax_head, 0)
        difference = gstr1_amt - gstr3b_amt
        if abs(difference) > TOLERANCE:
            diffs.append(ReconciliationException(
                recon_type="GSTR1_VS_GSTR3B",
                period=period, reason=classify_reason(tax_head, difference),
                books_amount=gstr1_amt, return_amount=gstr3b_amt,
                difference=difference,
                risk_level=score_risk(difference, materiality=engagement.performance_materiality),
                suggested_action="Obtain reconciliation statement; verify credit notes and RCM entries"
            ))
    return diffs

def classify_reason(tax_head, difference):
    # deterministic rule lookup, not LLM-guessed
    if tax_head == "credit_note" and difference != 0:
        return "Credit note not reflected in GSTR-3B"
    if tax_head == "export" and difference > 0:
        return "Export invoices reported with delay"
    return "Unclassified — requires manual review"
```

---

## 22. Sample TDS Reconciliation Logic (pseudocode)

```python
def reconcile_tds(engagement_id, quarter):
    ledger = load_tds_ledger(engagement_id, quarter)     # from books
    challans = load_challans(engagement_id, quarter)
    tds_return = load_tds_return(engagement_id, quarter)

    results = []
    for section, deducted in ledger.by_section().items():
        paid = challans.sum_by_section(section)
        reported = tds_return.sum_by_section(section)

        rule = rule_engine.get("TDS_THRESHOLD_RATE", section, as_of=quarter.end_date)
        expected_rate = rule.rate

        status = "Matched"
        if deducted > paid:
            status = "Deduction without full payment — interest exposure under Sec 201(1A)"
        elif paid > deducted:
            status = "Payment exceeds ledger deduction — possible unrecorded liability"
        if reported < deducted:
            status = "Return under-reports deductee credit"

        interest = calc_201_1a_interest(deducted, paid, rule) if status != "Matched" else 0

        results.append(TDSException(section=section, deducted=deducted, paid=paid,
                                     returned=reported, status=status,
                                     interest_exposure=interest))
    return results
```

---

## 23. Sample Audit Risk Calculation

```python
def compute_risk_score(category, factors: dict) -> RiskResult:
    """
    factors example for 'Revenue':
      { 'revenue_growth_vs_receivable_growth_gap': 0.6,  # weight 25
        'year_end_concentration_pct': 0.35,               # weight 20
        'related_party_revenue_pct': 0.15,                # weight 15
        'gst_books_mismatch_pct': 0.30,                    # weight 20
        'prior_year_misstatement_flag': 1,                 # weight 20 }
    """
    weights = RISK_WEIGHTS[category]   # versioned, stored in rule table
    raw = sum(factors[k] * weights[k] for k in weights)
    score = min(100, round(raw * 100))

    if score <= 20: level = "LOW"
    elif score <= 40: level = "MODERATE"
    elif score <= 60: level = "MEDIUM"
    elif score <= 80: level = "HIGH"
    else: level = "CRITICAL"

    return RiskResult(
        category=category, score=score, level=level,
        explanation=[f"{k}: {factors[k]} (weight {weights[k]})" for k in weights]
    )
```

Every score is stored with its contributing factors so the UI can always show *why* a category is HIGH, per Section BN's explainability requirement.

---

## 24. Sample Working Paper Structure (JSON schema, per Section BJ)

```json
{
  "id": "WP-GST-05",
  "objective": "Reconcile books turnover with GSTR-1 and GSTR-3B for FY 2025-26",
  "assertion": ["Completeness", "Accuracy"],
  "risk": { "category": "GST", "level": "HIGH", "score": 68 },
  "applicable_standard": ["CGST Act & Rules", "SA 500"],
  "population": "All outward supply invoices, FY 2025-26 (4,820 records)",
  "sample": { "method": "100% (system reconciliation)", "size": 4820 },
  "procedure": "System-reconciled books vs GSTR-1 vs GSTR-3B at monthly and annual level; manually reviewed all exceptions above performance materiality.",
  "evidence": ["sales_register.xlsx", "gstr1_mar26.json", "gstr3b_mar26.json"],
  "testing_result": { "matched": 4390, "partially_matched": 240, "unmatched": 190 },
  "exceptions": ["EXC-1042", "EXC-1043"],
  "conclusion": "PENDING — awaiting client response to EXC-1042 (₹21.8L turnover difference) before this working paper can be signed off.",
  "preparer": { "user_id": "u_101", "date": "2026-05-12" },
  "reviewer": { "user_id": "u_204", "date": null },
  "approver": null,
  "status": "IN_REVIEW",
  "version": 2
}
```

---

## 25. Sample Evidence Graph (per Section CD)

```json
{
  "root": { "type": "RevenueTransaction", "id": "TXN-88213", "amount": 1875000 },
  "edges": [
    { "from": "TXN-88213", "to": "Invoice:INV-4471", "relation": "evidenced_by" },
    { "from": "Invoice:INV-4471", "to": "Contract:CT-118", "relation": "governed_by" },
    { "from": "Invoice:INV-4471", "to": "EInvoice:IRN-92a7...", "relation": "reported_via" },
    { "from": "Invoice:INV-4471", "to": "CustomerLedger:CUST-0092", "relation": "posted_to" },
    { "from": "CustomerLedger:CUST-0092", "to": "BankReceipt:RCPT-7734", "relation": "settled_by" },
    { "from": "TXN-88213", "to": "GLEntry:JE-1042", "relation": "recorded_as" },
    { "from": "GLEntry:JE-1042", "to": "FinancialStatementLine:Revenue_from_Operations", "relation": "aggregates_into" },
    { "from": "FinancialStatementLine:Revenue_from_Operations", "to": "AuditProcedure:AP-REV-01", "relation": "tested_by" },
    { "from": "AuditProcedure:AP-REV-01", "to": "WorkingPaper:WP-REV-01", "relation": "documented_in" },
    { "from": "WorkingPaper:WP-REV-01", "to": "Reviewer:u_204", "relation": "signed_off_by" }
  ]
}
```

The graph is queryable in both directions — from a financial statement line down to the originating transaction, or from a single invoice up to the audit conclusion that relied on it — satisfying the "no black-box conclusion" requirement (Section BH).

---

### Next step

Per the phase-wise roadmap (Section 15), Phase 2 is the database schema and Universal Data Model in full — turning Section 20's illustrative DDL into the complete entity set from Section 5. Say the word and I'll build that out, or point me at a different phase to prioritize first.
