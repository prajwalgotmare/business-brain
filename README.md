# Business Brain

Business Brain is a governed enterprise operations agent for a synthetic omnichannel
consumer-goods company, **Aura Brands**. It joins e-commerce, logistics, and commercial
finance data to answer cited questions, perform read-only analytics, and draft controlled
business actions for human approval.

The project is designed as a measurable Applied AI engineering portfolio system rather
than a generic chatbot.

## Current status

Phase 1 foundation:

- FastAPI application factory
- Typed environment configuration
- Public health endpoint
- Secret-safe test coverage
- Ruff and Pytest CI workflow
- Local PostgreSQL and Qdrant services
- Locked product, role, risk, and completion contract

Phase 2A model routing:

- Groq primary model: `openai/gpt-oss-120b`
- Groq fallback model: `qwen/qwen3.8-27b`
- Typed request, response, token-usage, and provider-error contracts
- Automatic fallback on transient/model-availability failures
- No fallback on shared authentication or invalid-request failures

Phase 2B reliability:

- Bounded exponential retries with configurable jitter
- Primary-model circuit breaker with closed, open, and half-open states
- Automatic fallback after primary retry exhaustion or while its circuit is open
- Deterministic tests for retry timing, circuit recovery, and failure classification

Phase 2C API boundary:

- Validated `POST /api/v1/ask` request and response contracts
- Correlation IDs returned in both response bodies and `X-Request-ID` headers
- Explicit mock `X-Tenant-ID`, `X-User-ID`, and `X-Role` development headers
- Tenant and role context passed to generation without exposing user identifiers
- Sanitized validation and provider error responses

Phase 2D observability:

- Langfuse Python SDK v4 generation observations
- Tenant, role, request, thread, model, fallback, attempts, latency, and token context
- No authenticated user identifier exported to tracing
- Configurable prompt/response content capture for synthetic demonstration data
- Fail-open tracing: initialization, update, export, or flush failures cannot break generation

Phase 3A data foundation (in progress):

- Canonical e-commerce, logistics, procurement, finance, document, and approval model
- Tenant-scoped identifiers, sensitivity classes, and cross-entity integrity rules
- Standards-informed CSV, JSON, PostgreSQL, and Qdrant data flow contract
- Deterministic demonstration scenarios with planned evaluation ground truth
- Strict machine-readable reference catalog and generated JSON Schema
- Fixed Aura/Apex tenants, regions, products, warehouses, suppliers, and carriers
- Deterministic six-week commerce and inventory generator
- Tenant-separated customer, order, order-line, balance, and movement CSV files
- Reconciled order totals, inventory roll-forwards, allocations, and cross-tenant checks
- Deterministic logistics generator for outbound orders and inbound replenishment
- Tenant-separated shipments, items, tracking events, SLA facts, exceptions, and manifests
- Reconciled shipment charges, lifecycle events, SLA outcomes, and provisional penalty credits
- Public-source calibration manifest with UCI licensing and aggregate transaction statistics
- Reconciled purchase orders, supplier/carrier invoices, payments, and regional margins
- Six deterministic business scenarios with machine-readable answers and record evidence
- Deterministic data-quality manifest with row counts, tenant checks, and SHA-256 hashes
- Source-grounded PDF corpus with ten Aura documents and two CC BY 4.0 contract references
- Versioned Neon PostgreSQL schema with 23 tenant-safe relational tables and operational indexes
- Idempotent Aura/Apex ingestion with 9,392 live rows, provenance, integrity checks, and count verification

## Local development

Prerequisites: Python 3.11+, `uv`, Docker Desktop, and Docker Compose.

```powershell
Copy-Item .env.example .env
uv sync --all-groups
uv run uvicorn business_brain.main:app --reload
```

Open `http://127.0.0.1:8000/docs` or request:

```text
GET http://127.0.0.1:8000/api/v1/health
```

Run quality checks:

```powershell
uv run ruff check .
uv run pytest
```

Start local state services when needed:

```powershell
docker compose up -d
```

Configure Neon with the pooled application URL and direct administrative URL in `.env`:

```text
DATABASE_URL=postgresql://...-pooler...?sslmode=require
DATABASE_URL_DIRECT=postgresql://...?sslmode=require
```

Apply pending migrations, idempotently seed both demo tenants, and verify every table:

```powershell
uv run python -m business_brain.db
```

The command never prints either connection string. Do not commit `.env`.

## Delivery phases

1. Foundation and contract
2. Resilient Groq/Gemini gateway with Langfuse tracing
3. Data ingestion, hybrid retrieval, citations, and SQL analytics
4. LangGraph state, human approval, Auth0 RBAC, and adversarial security tests
5. Evaluation gates, forecasting, and experiment tracking
6. React demonstration UI, deployment, documentation, and measured portfolio evidence

See [`docs/product-contract.md`](docs/product-contract.md) for the locked MVP scope and
[`docs/data-blueprint.md`](docs/data-blueprint.md) for the canonical Phase 3 data contract.
Progress is maintained in [`docs/project-tracker.md`](docs/project-tracker.md).
