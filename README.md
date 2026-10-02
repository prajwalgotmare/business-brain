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
