# Authenticated MCP Integration

Verified: 2026-10-03

Project A exposes a separate Model Context Protocol resource server using the official
Python MCP SDK and Streamable HTTP. It reuses the same Auth0 access tokens, tenant/role
claims, RBAC matrix, SQL services, and Qdrant retrieval service as the REST API.

## Tool surface

| MCP tool | Operation | Authorization source |
| --- | --- | --- |
| `search_documents` | Hybrid document retrieval with citations | Document-search capability plus Qdrant tenant/sensitivity filters |
| `get_stockout_risks` | Fixed stockout SQL analytic | Stockout capability plus authenticated SQL tenant predicate |
| `reconcile_freight` | Fixed shipment billing/SLA reconciliation | Freight capability plus authenticated SQL tenant predicate |
| `list_overdue_invoices` | Fixed overdue-invoice analytic | Accounts-payable capability plus authenticated SQL tenant predicate |
| `analyze_margin_variance` | Fixed regional weekly margin comparison | Executive margin capability plus authenticated SQL tenant predicate |

All five tools are marked read-only, non-destructive, idempotent, and closed-world. Their
input schemas do not contain `tenant_id`, `role`, SQL, collection names, or arbitrary tool
names. Tenant and role are injected from the verified bearer token.

The MCP server intentionally does not expose arbitrary SQL, raw database access, uploads,
action execution, approval mutation, purchase-order submission, or carrier-claim submission.

## Authentication flow

1. An MCP client connects to the Streamable HTTP endpoint with an Auth0 bearer token.
2. The MCP HTTP middleware rejects missing tokens before parsing or executing a tool call.
3. `BusinessBrainTokenVerifier` validates signature, issuer, audience, time, subject, tenant,
   and role using the existing Auth0 validator.
4. Only immutable tenant and role claims become an `AuthContext`.
5. Each tool calls the existing governed service, which performs capability and data-layer
   checks again.

The Auth0 API audience is shared with the REST API, so MCP token resource validation is
performed by the existing audience validator; SDK URL-resource matching is explicitly
disabled rather than pretending the audience equals the endpoint URL.

## Run locally

Set `AUTH_MODE=auth0`, the existing Auth0 settings, data-service settings, and:

```text
MCP_RESOURCE_SERVER_URL=http://127.0.0.1:8001/mcp
```

Then run the ASGI factory:

```powershell
uv run uvicorn business_brain.mcp.server:create_mcp_app --factory --host 127.0.0.1 --port 8001
```

Production must use an HTTPS `MCP_RESOURCE_SERVER_URL` and a matching public endpoint.

## Verification

- Official MCP SDK: 2.3.0
- Advertised read-only tools: 5
- MCP-specific tests: 9 passed
- Complete suite: 222 passed
- Ruff: passed

