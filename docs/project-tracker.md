# Business Brain Project Tracker

Last updated: 2026-10-03

This is the single progress tracker for Project A. Update it only after work is
implemented and verified. An account being created is not the same as its integration
being complete.

Status legend: `DONE` = implemented and verified, `ACTIVE` = current phase has started,
`TODO` = not started, `BLOCKED` = cannot proceed without an external dependency.

## Delivery tracker

| ID | Phase / step | Status | Completed evidence | Remaining work / exit condition |
| --- | --- | --- | --- | --- |
| 0.1 | Lock product purpose and audience | DONE | Aura Brands portfolio demo, recruiter/hiring-manager audience, and five priorities documented | None |
| 0.2 | Lock personas, tenancy, risks, actions, and success criteria | DONE | Aura/Apex tenants, four roles, three action-risk levels, security threats, and completion metrics documented | None |
| 1.1 | Repository and Python foundation | DONE | Public repository, Python 3.11+, `uv`, package layout, `.gitignore`, and environment template | None |
| 1.2 | FastAPI foundation | DONE | Application factory and public health endpoint | None |
| 1.3 | Local service foundation | DONE | Docker Compose definitions for PostgreSQL and Qdrant | Cloud services are connected later in Phase 3 |
| 1.4 | CI foundation | DONE | GitHub Actions runs Ruff and Pytest | Extend gates when data, security, and evaluation suites exist |
| 2.1 | Groq model gateway | DONE | `openai/gpt-oss-120b` primary and `qwen/qwen3.8-27b` fallback with typed contracts | None |
| 2.2 | Gateway reliability | DONE | Retry, jitter, circuit breaker, failure classification, and deterministic tests | None |
| 2.3 | Validated Ask API | DONE | `POST /api/v1/ask`, request/thread IDs, mock tenant/user/role headers, and safe errors | Replace mock identity with Auth0 in Phase 4 |
| 2.4 | Langfuse tracing | DONE | Live authentication and trace verified; model, tenant, role, tokens, fallback, attempts, and request metadata captured | Add retrieval, tool, workflow, and evaluation spans as those features are built |
| 3.1 | Canonical data blueprint | DONE | 21-entity commerce, inventory, logistics, finance, document, and approval contract committed in `docs/data-blueprint.md` | None |
| 3.2 | Machine-readable schemas and reference entities | DONE | Strict Pydantic catalog, generated JSON Schema, fixed seed, 2 tenants, 58 total SKUs including 50 Aura SKUs, 5 warehouses, 7 product suppliers, 5 freight-billing suppliers, 5 carriers, and isolation tests | None |
| 3.3 | Commerce and inventory generator | DONE | Deterministic six-week generator, 10 tenant-separated CSV files, 3,447 connected rows, generated JSON Schema, reconciled totals/inventory, and spreadsheet-runtime verification | None |
| 3.4 | Logistics generator | DONE | Deterministic generator produced 531 shipments, 1,096 shipment items, 1,696 tracking events, 531 SLA facts, 129 exceptions, and 531 manifests across isolated Aura/Apex datasets; schema, reconciliation tests, reproducibility checks, and spreadsheet-runtime inspection passed | None |
| 3.5 | Finance and procurement generator | DONE | Public-source calibration manifest plus deterministic purchase orders, supplier/carrier invoices, invoice lines, completed payments, and weekly regional margin snapshots; UBL-aligned structures and end-to-end financial reconciliations verified | None |
| 3.6 | Ground-truth business scenarios | DONE | Six schema-validated Aura answer keys connect exact source rows for stockout risk, carrier overbilling plus SLA credit, supplier terms, overdue invoice, West margin decline, and CFO-gated PO submission; future PDF clauses are explicitly marked as Step 3.8 dependencies | None |
| 3.7 | Data-quality suite and manifest | DONE | Deterministic manifest records every source artifact hash and all CSV row/column metadata; nine automated checks cover freshness, keys, totals, dates, inventory, tenant isolation, and scenario evidence | None |
| 3.8 | Source-grounded PDF corpus | DONE | Ten synthetic Aura PDFs plus two downloaded CC BY 4.0 CUAD references; scenario clauses, provenance, sensitivity, hashes, page counts, extractable text, and visual rendering verified | None |
| 3.9 | Neon structured-data ingestion | DONE | Neon Singapore project connected; immutable checksum migration created 23 tenant-safe relational tables and six operational indexes; idempotent upsert loaded and verified 9,392 Aura/Apex rows with provenance and composite tenant foreign keys; second run applied zero migrations with identical counts; Ruff and 85 tests passed | None |
| 3.10 | Qdrant document ingestion | DONE | Free Frankfurt cluster connected; ten authorized synthetic PDFs produced 49 deterministic clause-aware chunks; local BGE-small dense plus BM25 sparse embeddings synchronized to `business_brain_documents_v1`; six payload indexes, source hashes, required clauses, exact counts, idempotent rerun, Aura/Apex tenant boundary, and four role visibility profiles verified; Ruff and 93 tests passed | None |
| 3.11 | Hybrid retrieval with citations | DONE | Governed API performs BGE dense plus BM25 sparse candidate search, Qdrant RRF fusion, deterministic business-identifier reranking, and typed document/page/section/clause/chunk citations; canonical tenant header fixed across API/Neon/Qdrant; five live expected citations ranked first with zero support-to-executive and Apex-to-Aura leaks; Ruff and 99 tests passed | None |
| 3.12 | Governed SQL analytics | DONE | Four fixed parameterized Neon operations cover stockout risk, freight reconciliation, overdue invoices, and regional margin variance; explicit read-only transactions, statement timeout, canonical tenant predicates, pre-query role gates, typed API results, and sanitized 400/403/503 errors implemented; all locked scenario facts matched live and Apex queries returned zero Aura records; Ruff and 106 tests passed | None |
| 3.13 | Website/API file-upload ingestion | DONE | Two-phase multipart API supports tracking-event and vendor-invoice CSV/JSON plus business-document PDF; authenticated tenant is injected server-side, resource/sensitivity role policy enforced, previews and raw bytes/status staged in Neon with expiry metadata, explicit commit required, and invalid/cross-tenant/spoofed/active-content/formula-like inputs quarantined; live PDF preview-to-Qdrant commit, JSON tenant tagging, persistent status, repeatable corpus coexistence, and zero cross-tenant status leakage verified; Ruff and 113 tests passed | Website UI consumes these APIs in Phase 6 |
| 4.1 | LangGraph governed supervisor | TODO | — | Add persistent state, routing, structured decisions, and bounded failure paths |
| 4.2 | Specialized tool nodes | TODO | — | Add SQL/analytics, hybrid RAG, and validated action-drafting nodes |
| 4.3 | Action schemas and risk policy | TODO | — | Add Pydantic PO, carrier-dispute, AP reminder, and delay-email outputs with policy-derived risk |
| 4.4 | Human approval workflow | TODO | — | Add interrupt/resume edges and manager/accountant/CFO approval rules |
| 4.5 | Durable checkpoints | TODO | — | Persist LangGraph checkpoints in Neon and prove restart recovery for pending approvals |
| 4.6 | Auth0 identity integration | TODO | — | Create/configure account, validate OIDC JWTs, and map immutable tenant/role claims |
| 4.7 | RBAC and tenant enforcement | TODO | — | Enforce policy at API, tool, SQL, Qdrant, document, and action boundaries |
| 4.8 | Adversarial security suite | TODO | — | Test cross-tenant retrieval, privilege escalation, prompt injection, and unauthorized tool execution |
| 4.9 | MCP integration | TODO | — | Expose or consume narrowly scoped governed tools with authentication and schema validation |
| 5.1 | Golden evaluation dataset | TODO | — | Create and version at least 50 questions with expected facts, citations, permissions, and refusal behavior |
| 5.2 | RAGAS and task-quality metrics | TODO | — | Measure groundedness, faithfulness/relevance as selected, citation accuracy, routing, and tool correctness |
| 5.3 | CI evaluation gates | TODO | — | Block regressions below locked quality/security thresholds and publish reports |
| 5.4 | Demand/stockout forecasting | TODO | — | Build leakage-safe baseline and XGBoost model using time-aware validation |
| 5.5 | DagsHub experiment tracking | TODO | — | Create/configure account and track data/model versions, parameters, metrics, and artifacts |
| 5.6 | Performance and cost evaluation | TODO | — | Measure retrieval/tool P95, end-to-end generation latency, token use, fallback rate, and free-tier fit |
| 6.1 | Demonstration web application | TODO | — | Build role-switchable dashboard, chat, analytics, citations, draft actions, uploads, and approval UI |
| 6.2 | Instant demo identity flow | TODO | — | Provide safe preconfigured demo personas without exposing secrets |
| 6.3 | Public deployment | TODO | — | Configure Cloudflare/Vercel and backend/data services within verified zero-card free tiers |
| 6.4 | End-to-end acceptance suite | TODO | — | Verify all five core questions, four draft actions, approvals, crash recovery, isolation, and failure states |
| 6.5 | Portfolio documentation | TODO | — | Complete README, architecture diagrams, threat model, demo script, measurements, and limitations |
| 6.6 | Resume and interview evidence | TODO | — | Produce honest metric-backed bullets, system-design narrative, and reproducible live-demo evidence |
| 6.7 | Final completion audit | TODO | — | Confirm live URL, quality threshold, latency evidence, zero security-suite failures, crash-resume, and documentation |

## Accounts and external services

Account readiness is tracked separately because credentials alone do not prove working
application integration.

| Service | Account status | Integration status | Used in |
| --- | --- | --- | --- |
| GitHub | Ready | DONE | Repository, pull requests, and CI |
| Groq Cloud | Ready | DONE | Primary and fallback LLM gateway |
| Google AI Studio | Ready | Not currently required | Optional experimentation/future fallback only |
| Langfuse Cloud | Ready | DONE for LLM traces | Extend during retrieval, tools, workflows, and evaluations |
| Kaggle | Ready | TODO | Public dataset reference/download and optional notebook work |
| Hugging Face | Ready | TODO | Embedding/model access if selected |
| Qdrant Cloud | Ready | DONE for document ingestion | Use existing dense+sparse collection for hybrid retrieval in Step 3.11 |
| Neon Postgres | Ready | DONE for structured demo data | Extend for LangGraph checkpoints and durable application state in Phase 4 |
| Cloudflare | Pending | TODO | Hosting/edge capability selected during deployment design |
| Auth0 | Pending | TODO | Production-style OIDC authentication and claims |
| DagsHub | Pending | TODO | Forecasting experiment tracking |
| Vercel | Pending | TODO | Public demonstration frontend/deployment |

## Current checkpoint

- Current completed step: **3.13 Website/API file-upload ingestion**
- Next step: **4.1 LangGraph governed supervisor**
- Active Git branch: `feat/data-blueprint`
- Latest verification at this checkpoint: live PDF preview/commit created five governed Qdrant points, valid JSON was tenant-tagged, cross-tenant JSON was quarantined, upload status was invisible across tenants, original corpus rerun preserved uploaded points, Ruff passed, and 113 tests passed

## Update rule

For every step:

1. Keep its status `TODO` until implementation begins.
2. Use `ACTIVE` only while that specific step is being implemented.
3. Change it to `DONE` only after proportionate automated or manual verification.
4. Record the concrete evidence, test result, commit, or live-service check.
5. Update the current checkpoint and next step before moving forward.
