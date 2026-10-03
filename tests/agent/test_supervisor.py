from collections import deque

import pytest

from business_brain.agent.schemas import AgentRoute, SupervisorIntent, WorkflowStatus
from business_brain.agent.supervisor import GovernedSupervisor
from business_brain.llm.gateway import AllModelsFailedError
from business_brain.llm.schemas import GenerationResult, TokenUsage
from business_brain.observability.tracing import NoOpGenerationTracer
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


def routing_json(route: str, intent: str, risk: str = "low") -> str:
    return (
        '{"route":"'
        + route
        + '","intent":"'
        + intent
        + '","risk_level":"'
        + risk
        + '","rationale":"Required capability","confidence":0.98}'
    )


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


def supervisor(responses) -> tuple[GovernedSupervisor, StubGateway]:
    gateway = StubGateway(responses)
    return (
        GovernedSupervisor(
            gateway=gateway,
            tracer=NoOpGenerationTracer(),
            primary_model="openai/gpt-oss-120b",
        ),
        gateway,
    )


@pytest.mark.asyncio
async def test_authorized_business_request_is_routed_once() -> None:
    agent, gateway = supervisor(
        [generation(routing_json("sql_analytics", "stockout_risk"))]
    )

    result = await run(agent, UserRole.LOGISTICS_MANAGER)

    assert result.route == AgentRoute.SQL_ANALYTICS
    assert result.intent == SupervisorIntent.STOCKOUT_RISK
    assert result.status == WorkflowStatus.ROUTED
    assert result.supervisor_attempts == 1
    assert len(gateway.requests) == 1


@pytest.mark.asyncio
async def test_policy_denies_financial_request_before_tool_execution() -> None:
    agent, gateway = supervisor(
        [generation(routing_json("sql_analytics", "margin_analysis", "high"))]
    )

    result = await run(agent, UserRole.SUPPORT_INTERN)

    assert result.route == AgentRoute.REFUSE
    assert result.status == WorkflowStatus.REFUSED
    assert result.error_code == "policy_denied"
    assert len(gateway.requests) == 1


@pytest.mark.asyncio
async def test_malformed_router_output_fails_closed_without_looping() -> None:
    agent, gateway = supervisor([generation("not-json")])

    result = await run(agent, UserRole.FOUNDER_CFO)

    assert result.status == WorkflowStatus.FAILED
    assert result.error_code == "supervisor_failure"
    assert result.supervisor_attempts == 1
    assert len(gateway.requests) == 1


@pytest.mark.asyncio
async def test_extra_model_fields_fail_closed() -> None:
    payload = routing_json("sql_analytics", "margin_analysis")[:-1] + ',"tenant_id":"other"}'
    agent, _ = supervisor([generation(payload)])

    result = await run(agent, UserRole.FOUNDER_CFO)

    assert result.status == WorkflowStatus.FAILED
    assert result.error_code == "supervisor_failure"


@pytest.mark.asyncio
async def test_direct_response_uses_second_bounded_generation_and_aggregates_usage() -> None:
    agent, gateway = supervisor(
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
    agent, gateway = supervisor([AllModelsFailedError("unavailable")])

    result = await run(agent, UserRole.FOUNDER_CFO)

    assert result.status == WorkflowStatus.FAILED
    assert result.error_code == "supervisor_failure"
    assert len(gateway.requests) == 1
