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
| 3.2 | Machine-readable schemas and reference entities | TODO | — | Implement validated schemas plus two tenants, regions, 50 Aura SKUs, warehouses, suppliers, and carriers |
| 3.3 | Commerce and inventory generator | TODO | — | Deterministically generate customers, orders, order lines, balances, and inventory movements |
| 3.4 | Logistics generator | TODO | — | Generate shipments, tracking events, delays, inbound replenishment, and carrier SLA facts |
| 3.5 | Finance and procurement generator | TODO | — | Generate purchase orders, vendor invoices, invoice lines, payments, freight charges, and margin inputs |
| 3.6 | Ground-truth business scenarios | TODO | — | Plant stockout, overbilling, commercial-terms, overdue-invoice, West-margin, and PO-approval scenarios |
| 3.7 | Data-quality suite and manifest | TODO | — | Validate keys, totals, dates, inventory, tenant isolation, scenario evidence, row counts, and file hashes |
| 3.8 | Synthetic PDF corpus | TODO | — | Create and verify 8–12 supplier agreements, carrier agreements, invoices, policies, and compliance documents |
| 3.9 | Neon structured-data ingestion | TODO | — | Create account/database, migrations, tenant-safe ingestion, indexes, and reproducible seed process |
| 3.10 | Qdrant document ingestion | TODO | — | Create account/cluster, extraction, chunking, embeddings, metadata, and mandatory tenant/sensitivity filters |
| 3.11 | Hybrid retrieval with citations | TODO | — | Implement dense plus keyword retrieval, reranking, clause/page citations, and retrieval tests |
| 3.12 | Governed SQL analytics | TODO | — | Implement read-only tenant-scoped queries for inventory, shipping, invoices, and margins |
| 3.13 | Website/API file-upload ingestion | TODO | — | Authorized CSV/JSON/PDF upload, validation, preview, tenant tagging, quarantine, and ingestion status |
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
| Qdrant Cloud | Pending | TODO | Hybrid document retrieval |
| Neon Postgres | Pending | TODO | Structured data, checkpoints, and durable application state |
| Cloudflare | Pending | TODO | Hosting/edge capability selected during deployment design |
| Auth0 | Pending | TODO | Production-style OIDC authentication and claims |
| DagsHub | Pending | TODO | Forecasting experiment tracking |
| Vercel | Pending | TODO | Public demonstration frontend/deployment |

## Current checkpoint

- Current completed step: **3.1 Canonical data blueprint**
- Next step: **3.2 Machine-readable schemas and reference entities**
- Active Git branch: `feat/data-blueprint`
- Latest verification at this checkpoint: Ruff passed and 32 tests passed

## Update rule

For every step:

1. Keep its status `TODO` until implementation begins.
2. Use `ACTIVE` only while that specific step is being implemented.
3. Change it to `DONE` only after proportionate automated or manual verification.
4. Record the concrete evidence, test result, commit, or live-service check.
5. Update the current checkpoint and next step before moving forward.
