import json
from collections import deque
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from business_brain.agent.schemas import AgentRoute, RiskLevel, SupervisorIntent, WorkflowStatus
from business_brain.agent.supervisor import GovernedSupervisor
from business_brain.analytics.schemas import StockoutRisk
from business_brain.llm.gateway import AllModelsFailedError
from business_brain.llm.schemas import GenerationResult, TokenUsage
from business_brain.observability.tracing import NoOpGenerationTracer
from business_brain.retrieval.schemas import DocumentCitation, HybridSearchResult, RetrievalHit
from business_brain.security.context import AuthContext, UserRole


class StubGateway:
    def __init__(self, responses: list[GenerationResult | Exception]) -> None:
        self.responses = deque(responses)
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response


def generation(content: str, *, fallback: bool = False) -> GenerationResult:
    return GenerationResult(
        content=content,
        model="llama-3.3-70b-versatile" if fallback else "openai/gpt-oss-120b",
        used_fallback=fallback,
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def routing_json(route: str, intent: str, risk: str = "low", arguments=None) -> str:
    return json.dumps(
        {
            "route": route,
            "intent": intent,
            "risk_level": risk,
            "rationale": "Required capability",
            "confidence": 0.98,
            "arguments": arguments or {},
        }
    )


def purchase_order_payload() -> dict:
    return {
        "supplier_id": "sup_aur_packaging",
        "warehouse_id": "wh_aur_west",
        "expected_delivery_date": "2026-10-15",
        "currency_code": "USD",
        "lines": [
            {
                "product_id": "prd_aur_006",
                "sku": "AUR-SKN-006",
                "quantity": 300,
                "unit_cost": "11.37",
                "line_amount": "3411.00",
            }
        ],
        "subtotal_amount": "3411.00",
        "tax_amount": "0.00",
        "freight_amount": "125.00",
        "total_amount": "3536.00",
        "notes": "Replenishment for West warehouse",
    }


def auth(role: UserRole) -> AuthContext:
    return AuthContext(tenant_id="tenant_aura", user_id="test-user", role=role)


async def run(supervisor: GovernedSupervisor, role: UserRole, question: str = "test request"):
    return await supervisor.run(
        request_id="req-test",
        thread_id="9c825d3b-b21c-4425-87f4-416597203a3b",
        auth=auth(role),
        question=question,
        max_tokens=128,
    )


class StubAnalytics:
    def __init__(self) -> None:
        self.calls = []

    def stockout_risks(self, auth, *, limit):
        self.calls.append((auth, limit))
        return [
            StockoutRisk(
                product_id="prd_aur_006",
                sku="AUR-SKN-006",
                warehouse_id="wh_aur_west",
                snapshot_at=datetime(2026, 9, 21, tzinfo=UTC),
                available_quantity=2,
                reorder_point=59,
                demand_14d=7,
                projected_demand_7d=Decimal("3.5"),
                delayed_inbound_quantity=213,
            )
        ]


class StubRetriever:
    def __init__(self) -> None:
        self.calls = []

    def search(self, query, auth, *, limit):
        self.calls.append((query, auth, limit))
        citation = DocumentCitation(
            document_id="doc_aur_supplier_msa",
            title="Packaging Supplier Agreement",
            page_number=2,
            clause_id="clause_terms_2_1",
            section_heading="Payment Terms",
            chunk_id="chunk-1",
        )
        return HybridSearchResult(
            query=query,
            tenant_id=auth.tenant_id,
            role=auth.role.value,
            candidate_count=1,
            hits=[
                RetrievalHit(
                    chunk_id="chunk-1",
                    content="Payment terms are Net-30.",
                    sensitivity="executive",
                    fusion_score=0.8,
                    rerank_score=0.9,
                    citation=citation,
                )
            ],
        )


def supervisor(responses) -> tuple[GovernedSupervisor, StubGateway, StubAnalytics, StubRetriever]:
    gateway = StubGateway(responses)
    analytics = StubAnalytics()
    retriever = StubRetriever()
    return (
        GovernedSupervisor(
            gateway=gateway,
            tracer=NoOpGenerationTracer(),
            primary_model="openai/gpt-oss-120b",
            analytics_service=analytics,
            retriever=retriever,
        ),
        gateway,
        analytics,
        retriever,
    )


@pytest.mark.asyncio
async def test_authorized_sql_request_executes_fixed_tool_and_is_answered() -> None:
    agent, gateway, analytics, _ = supervisor(
        [
            generation(routing_json("sql_analytics", "stockout_risk")),
            generation("AUR-SKN-006 is at risk with 2 units available."),
        ]
    )

    result = await run(agent, UserRole.LOGISTICS_MANAGER)

    assert result.route == AgentRoute.SQL_ANALYTICS
    assert result.intent == SupervisorIntent.STOCKOUT_RISK
    assert result.status == WorkflowStatus.COMPLETED
    assert result.tool_name == "stockout_risk"
    assert result.tool_result[0]["sku"] == "AUR-SKN-006"
    assert result.supervisor_attempts == 1
    assert len(gateway.requests) == 2
    assert analytics.calls[0][0].tenant_id == "tenant_aura"


@pytest.mark.asyncio
async def test_policy_denies_financial_request_before_tool_execution() -> None:
    agent, gateway, analytics, _ = supervisor(
        [generation(routing_json("sql_analytics", "margin_analysis", "high"))]
    )

    result = await run(agent, UserRole.SUPPORT_INTERN)

    assert result.route == AgentRoute.REFUSE
    assert result.status == WorkflowStatus.REFUSED
    assert result.error_code == "policy_denied"
    assert len(gateway.requests) == 1
    assert analytics.calls == []


@pytest.mark.asyncio
async def test_malformed_router_output_fails_closed_without_looping() -> None:
    agent, gateway, _, _ = supervisor([generation("not-json")])

    result = await run(agent, UserRole.FOUNDER_CFO)

    assert result.status == WorkflowStatus.FAILED
    assert result.error_code == "supervisor_failure"
    assert result.supervisor_attempts == 1
    assert len(gateway.requests) == 1


@pytest.mark.asyncio
async def test_extra_model_fields_fail_closed() -> None:
    payload = routing_json("sql_analytics", "margin_analysis")[:-1] + ',"tenant_id":"other"}'
    agent, _, _, _ = supervisor([generation(payload)])

    result = await run(agent, UserRole.FOUNDER_CFO)

    assert result.status == WorkflowStatus.FAILED
    assert result.error_code == "supervisor_failure"


@pytest.mark.asyncio
async def test_direct_response_uses_second_bounded_generation_and_aggregates_usage() -> None:
    agent, gateway, _, _ = supervisor(
        [
            generation(routing_json("direct_response", "general_conversation"), fallback=True),
            generation("Hello. How can I help?"),
        ]
    )

    result = await run(agent, UserRole.SUPPORT_INTERN, "hello")

    assert result.status == WorkflowStatus.COMPLETED
    assert result.answer == "Hello. How can I help?"
    assert result.used_fallback is True
    assert result.usage.total_tokens == 30
    assert len(gateway.requests) == 2


@pytest.mark.asyncio
async def test_provider_failure_terminates_safely() -> None:
    agent, gateway, _, _ = supervisor([AllModelsFailedError("unavailable")])

    result = await run(agent, UserRole.FOUNDER_CFO)

    assert result.status == WorkflowStatus.FAILED
    assert result.error_code == "supervisor_failure"
    assert len(gateway.requests) == 1


@pytest.mark.asyncio
async def test_retrieval_tool_returns_structured_citations() -> None:
    agent, gateway, _, retriever = supervisor(
        [
            generation(routing_json("document_retrieval", "supplier_terms")),
            generation("The agreement specifies Net-30 terms [1]."),
        ]
    )

    result = await run(agent, UserRole.FOUNDER_CFO, "What are our supplier payment terms?")

    assert result.status == WorkflowStatus.COMPLETED
    assert result.tool_name == "hybrid_retrieval"
    assert result.citations[0].clause_id == "clause_terms_2_1"
    assert retriever.calls[0][1].tenant_id == "tenant_aura"
    assert len(gateway.requests) == 2


@pytest.mark.asyncio
async def test_action_node_creates_draft_only_artifact_with_deterministic_risk() -> None:
    agent, gateway, _, _ = supervisor(
        [
            generation(
                routing_json("action_drafting", "draft_purchase_order", risk="low")
            ),
            generation(json.dumps(purchase_order_payload())),
        ]
    )

    result = await run(agent, UserRole.FOUNDER_CFO, "Draft a replenishment purchase order")

    assert result.status == WorkflowStatus.COMPLETED
    assert result.risk_level.value == "high"
    assert result.action_draft is not None
    assert result.action_draft["approval_required"] is True
    assert result.action_draft["submission_allowed"] is False
    assert result.action_draft["required_approver_roles"] == ["founder_cfo"]
    assert result.action_draft["payload"]["total_amount"] == "3536.00"
    assert len(gateway.requests) == 2


@pytest.mark.asyncio
async def test_invalid_action_payload_fails_closed() -> None:
    invalid = purchase_order_payload() | {"total_amount": "1.00"}
    agent, gateway, _, _ = supervisor(
        [
            generation(routing_json("action_drafting", "draft_purchase_order")),
            generation(json.dumps(invalid)),
        ]
    )

    result = await run(agent, UserRole.FOUNDER_CFO, "Draft a purchase order")

    assert result.status == WorkflowStatus.FAILED
    assert result.error_code == "invalid_draft"
    assert result.risk_level == RiskLevel.HIGH
    assert result.action_draft is None
    assert len(gateway.requests) == 2


@pytest.mark.asyncio
async def test_missing_required_tool_arguments_fails_without_guessing() -> None:
    agent, gateway, _, _ = supervisor(
        [generation(routing_json("sql_analytics", "freight_reconciliation"))]
    )

    result = await run(agent, UserRole.STAFF_ACCOUNTANT, "Reconcile a freight shipment")

    assert result.status == WorkflowStatus.FAILED
    assert result.error_code == "tool_arguments_missing"
    assert len(gateway.requests) == 1
