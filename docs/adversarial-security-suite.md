# Adversarial Security Suite

Verified: 2026-10-03

Project A treats model output, user prompts, retrieved text, uploaded data, and client
headers as untrusted. Authorization decisions are made by deterministic application
policy using the identity validated from the access token.

## Executable attack coverage

The versioned corpus in `tests/security/adversarial_corpus.json` covers:

- prompt instructions that claim CFO or system authority;
- attempts to retrieve supplier pricing, margins, invoices, or another tenant's data;
- attempts to invoke purchase-order, carrier-dispute, or payment tools without permission;
- SQL-like strings, tenant overrides, extra fields, and excessive limits in tool arguments;
- model-proposed route/intent confusion;
- Qdrant results containing the wrong tenant or an unauthorized sensitivity.

The suite contains 21 adversarial cases. Every case is executable and runs in CI through
`tests/security/test_adversarial_suite.py`.

## Security invariants proved

1. A prompt cannot change the authenticated tenant or role.
2. A model routing decision cannot grant a capability the role does not possess.
3. Unauthorized requests are refused before any analytics, retrieval, or action tool runs.
4. Tool arguments must pass strict schemas and cannot supply a tenant identifier.
5. SQL operations use fixed parameterized statements with the authenticated tenant.
6. Qdrant applies tenant and sensitivity filters to both retrieval branches and the fused
   query, then independently validates every returned payload.
7. Uploaded records, approvals, and durable threads remain scoped to their authenticated
   tenant and role.
8. Draft approval never enables external submission; `submission_allowed` remains false.

## Result

- Adversarial cases: 21
- Adversarial failures: 0
- Complete test suite: 213 passed
- Ruff: passed

This suite validates application-layer controls. It does not claim that arbitrary language
models are intrinsically immune to prompt injection; instead, sensitive data and tools are
kept outside the model's reach unless deterministic authorization succeeds.
