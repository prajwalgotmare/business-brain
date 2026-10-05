# Resume and Interview Evidence

## Resume bullets

- Built a governed FastAPI/LangGraph operations copilot for commerce, logistics, and
  finance, routing requests to fixed SQL analytics, cited hybrid retrieval, or
  approval-gated draft actions across four roles and two tenants.
- Implemented tenant/RBAC enforcement across Neon, Qdrant, uploads, MCP, and agent
  workflows; passed 21 adversarial security cases with a 100% pass rate.
- Delivered a 50-case evaluation harness with 96.9% groundedness and 90% citation
  recall, plus Langfuse tracing, retries, fallback routing, and sanitized request IDs.
- Built durable Neon-backed LangGraph checkpoints so pending approvals survive process
  and connection restarts; approved drafts remain explicitly unexecuted.
- Deployed the demo to Vercel and verified live health, stockout analytics, structured
  answers, failure details, and responsive answer formatting.

## System-design narrative

The key design decision is to make the model a router and language interface, not the
security boundary. Authenticated tenant/role context enters the API, deterministic
policy checks the requested intent, and only fixed tools receive schema-bounded
arguments. SQL and Qdrant enforce tenant predicates independently. Any external action
is a draft that pauses at a durable approval interrupt; no model output can submit it.

Reliability is layered: provider retries and fallback protect generation, retrieval
failure degrades safely, Langfuse is fail-open, and Neon checkpoints restore interrupted
workflows without another LLM call. The evaluation gate then measures groundedness,
citations, routing, permissions, actions, latency, and runtime errors.

## Interview demo flow

1. Run the stockout question and explain the fixed SQL route and risk calculation.
2. Run supplier terms and point to page/clause citations from Qdrant.
3. Switch roles and show a deterministic authorization refusal.
4. Request a purchase-order draft, show the pending approval, restart/resume it, and
   emphasize that submission remains disabled.
5. Trigger a validation error and expand technical details using its request ID.
