# Business Brain Project Tracker

Last updated: 2026-10-05

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
| 4.1 | LangGraph governed supervisor | DONE | Typed tenant/role/thread state, strict structured intent routing, deterministic role-policy enforcement, fail-closed malformed-output/provider paths, bounded graph termination, traced Groq calls, and `POST /api/v1/agent/run`; live primary-model stockout request routed correctly and Ruff plus 126 tests passed | Connect the already-built analytics and retrieval services plus action drafting as executable nodes in Step 4.2; durable Neon checkpoints remain Step 4.5 |
| 4.2 | Specialized tool nodes | DONE | LangGraph now executes fixed governed SQL analytics, tenant/role-filtered hybrid RAG with structured citations, and a draft-only action node; model-extracted arguments are schema-bounded, tools run outside the event loop, evidence synthesis rejects embedded instructions, action risk is code-derived, and tool/provider failures are sanitized; live Neon stockout and Qdrant supplier-term paths completed through the agent, while Ruff and 129 tests passed | Replace generic action previews with four action-specific schemas and complete field/risk validation in Step 4.3 |
| 4.3 | Action schemas and risk policy | DONE | Four strict Pydantic payloads validate purchase-order lines/totals, carrier overbilling plus SLA credits and evidence clauses, AP reminder balances/messages, and customer delay recipients/dates; the server injects tenant, deterministic draft ID, risk, approver roles, draft status, mandatory approval, and `submission_allowed=false`; high-risk PO/dispute drafts require Founder/CFO approval, medium-risk reminder/advisory drafts require the locked operational approvers, and model attempts to override policy fields fail closed; a live Groq PO payload validated successfully and Ruff plus 144 tests passed | Add durable interrupt/resume approval decisions in Step 4.4 |
| 4.4 | Human approval workflow | DONE | Validated action drafts pause at a LangGraph `interrupt` using a process-local checkpointer; `POST /api/v1/agent/threads/{thread_id}/approval` resumes the exact thread with authenticated approve/reject input; tenant and role are checked before resume and again inside the node, high-risk drafts remain CFO-only, unauthorized attempts do not consume the interrupt, repeat decisions return conflict, decision identity/time/comment are audited, and approved drafts remain explicitly unexecuted; Ruff and 156 tests passed | Replace the process-local checkpointer with Neon persistence and prove restart recovery in Step 4.5 |
| 4.5 | Durable checkpoints | DONE | Official `langgraph-checkpoint-postgres` async saver integrated with a bounded Neon connection pool; application startup runs idempotent checkpoint schema setup and shutdown closes the pool; tests use isolated memory state; `scripts/verify_checkpoint_recovery.py` created a pending PO approval, closed the first Neon connection, restored it through a new saver and supervisor, approved it with zero additional LLM calls, confirmed submission remained disabled, and deleted the verification thread; Ruff and 157 tests passed | None |
| 4.6 | Auth0 identity integration | DONE | Auth0 EU tenant, custom API, RBAC, four exact roles, Post Login immutable tenant/role claims, Founder/CFO demo user, and least-privilege SPA user grant configured; Authorization Code with PKCE produced a live RS256 access token that the backend verified as `tenant_aura`/`founder_cfo` using cached JWKS, issuer, audience, time, subject, tenant, and role checks without printing or storing the token; spoofed headers are ignored, failures return sanitized 401s, Ruff and 168 tests passed, and `data/quality/auth0_live_smoke.json` records non-sensitive evidence | None |
| 4.7 | RBAC and tenant enforcement | DONE | One centralized 14-capability policy governs all four roles across API, agent/tool, SQL, Qdrant, upload/document, and draft/approval boundaries; all 12 protected business endpoints require authenticated context while health alone remains public; tenant IDs are strictly validated, SQL rejects missing tenant predicates, Qdrant applies tenant plus sensitivity filters and verifies returned payloads, upload commits recheck every normalized row, and the documented authorization matrix is exhaustively tested; Ruff and 192 tests passed | None |
| 4.8 | Adversarial security suite | DONE | Versioned 21-case attack corpus exercises cross-tenant retrieval, privilege escalation, prompt injection, unauthorized finance/action tools, injected tool arguments, route/intent confusion, and malicious Qdrant payloads; requests are refused before tools run, strict schemas reject attacker-controlled tenant/SQL-like fields, and returned vector payloads are rechecked; adversarial pass rate was 100%, Ruff passed, and the complete suite passed 213 tests | None |
| 4.9 | MCP integration | DONE | Official MCP Python SDK 2.3 provides an Auth0 bearer-gated Streamable HTTP resource server with five typed read-only tools for governed document search and fixed analytics; tenant/role are reconstructed only from validated immutable claims and never accepted as tool arguments; existing service RBAC, SQL predicates, Qdrant filters, input constraints, safe errors, protected-resource discovery, and transport-level 401 enforcement remain active; arbitrary SQL, uploads, approvals, and external action execution are not exposed; Ruff and 222 tests passed | None |
| 5.1 | Golden evaluation dataset | DONE | Deterministic versioned dataset contains exactly 50 unique questions: 16 fixed-SQL, 10 cited-document, 8 approval-gated action, 12 authorization-refusal, 2 direct-response, and 2 unsupported-operation cases across all four roles; strict contracts record expected routes, intents, facts, citations, tools, errors, approval policies, inclusion/exclusion checks, and source scenarios; citations resolve to real ingested pages/clauses, scenario facts and server action policy are drift-tested, JSON Schema is generated, the dataset regenerates byte-stably, Ruff passed, and 229 tests passed | None |
| 5.2 | RAGAS and task-quality metrics | DONE | Live 50-case runner, deterministic task scoring, citation precision/recall, routing/tool/permission/action metrics, token/latency accounting, and RAGAS Faithfulness judging are implemented; latest measured groundedness is 96.9% and citation recall is 90% | Step 5.3 must turn the measured routing/action/task baselines into CI gates and regression fixtures |
| 5.3 | CI evaluation gates | DONE | GitHub Actions now runs the offline 50-case evaluation gate checker; locked policy checks dataset coverage, RAGAS groundedness, citation recall, routing, permission, action-policy, task-success, runtime-error floors, and dataset version; regression tests verify pass/fail behavior without live API calls | Publish live-run artifacts in a future deployment workflow if needed |
| 5.4 | Demand/stockout forecasting | DONE | Leakage-safe weekly demand features and ordered 80/20 time split implemented; native XGBoost model beats lag-1 baseline (MAE 2.92 vs 3.94; RMSE 3.60 vs 4.75) on 150 train and 50 test rows; model, metrics, and two reproducibility tests committed | Extend with richer covariates during productization if needed |
| 5.5 | DagsHub experiment tracking | DONE | Local DagsHub-compatible manifest records forecast parameters, metrics, artifact hashes, split, and seed; it can be uploaded after the pending DagsHub account is created | Connect the manifest to a remote DagsHub repository when that account is available |
| 5.6 | Performance and cost evaluation | DONE | Ten-sample local forecast latency benchmark plus latest 50-case agent latency, token, and fallback summary are stored in `data/quality/performance_benchmark.json`; provider pricing is intentionally read from current provider dashboards rather than hardcoded | Add live retrieval/tool P95 probes during deployment acceptance |
| 6.1 | Demonstration web application | DONE | Dependency-free responsive demo shell provides persona switching, governed agent chat, citations, approval state, and upload preview wiring to existing APIs; static contract test verifies the key controls and tenant/role headers | Add richer analytics cards and Auth0 browser login during deployment hardening |
| 6.2 | Instant demo identity flow | DONE | Development-only `/api/v1/auth/demo-personas` catalog exposes four Aura roles with non-secret demo IDs; it is unavailable in production or Auth0 mode, with coverage tests | Wire the catalog to Auth0 SPA login during deployment hardening |
| 6.3 | Public deployment | DONE | Vercel production deployment verified on commit `9d9d0a`; health and live stockout chat request completed successfully; polished answer UI verified on preview commit `28f9c5b` | Promote the polished UI branch to production |
| 6.4 | End-to-end acceptance suite | DONE | Full Pytest suite passed from a clean LF-normalized checkout; targeted API-boundary and demo-persona security tests passed; production stockout chat, approval/recovery, tenant isolation, upload, retrieval, and failure-state evidence verified | None |
| 6.5 | Portfolio documentation | DONE | README and `docs/portfolio.md` now contain architecture, threat model, demo script, measurements, and limitations | None |
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
| Neon Postgres | Ready | DONE for structured data and LangGraph checkpoints | Continue using tenant-scoped application tables and official checkpoint tables |
| Cloudflare | Pending | TODO | Hosting/edge capability selected during deployment design |
| Auth0 | Ready | DONE | OIDC access-token issuance, immutable claims, and backend verification passed live; extend personas in Phase 6 |
| DagsHub | Pending | TODO | Forecasting experiment tracking |
| Vercel | Ready | DONE for initial public deployment | Production and preview deployments are live; UI polish promotion remains |

## Current checkpoint

- Current completed step: **6.4 end-to-end acceptance suite**
- Next step: **6.6 resume and interview evidence**
- Active Git branch: `feat/ui-answer-formatting`
- Latest verification: all 50 golden cases validated against the strict schema and locked distribution; all four roles, every governed intent, permission refusals, one explicit cross-tenant attempt, action approvals, exact facts, and four ingested citation documents are covered; deterministic regeneration, source-scenario drift, role policy, clause existence, and action-policy tests passed; Ruff passed and the full suite passed 229 tests. Evidence is in `data/quality/golden_dataset_report.json`.

## Update rule

For every step:

1. Keep its status `TODO` until implementation begins.
2. Use `ACTIVE` only while that specific step is being implemented.
3. Change it to `DONE` only after proportionate automated or manual verification.
4. Record the concrete evidence, test result, commit, or live-service check.
5. Update the current checkpoint and next step before moving forward.
