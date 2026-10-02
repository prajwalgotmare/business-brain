from collections import deque

import pytest

from business_brain.llm.gateway import AllModelsFailedError, LLMGateway
from business_brain.llm.groq_client import LLMProviderError
from business_brain.llm.reliability import CircuitBreaker, CircuitState, RetryPolicy
from business_brain.llm.schemas import (
    ChatMessage,
    GenerationRequest,
    GenerationResult,
)


class StubGroqClient:
    def __init__(self, responses: list[GenerationResult | Exception]) -> None:
        self.responses = deque(responses)
        self.calls: list[str] = []

    async def generate(self, model: str, request: GenerationRequest) -> GenerationResult:
        self.calls.append(model)
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response


def request() -> GenerationRequest:
    message = ChatMessage(role="user", content="Summarize inventory risk")
    return GenerationRequest(messages=[message])


def result(model: str) -> GenerationResult:
    return GenerationResult(content="No immediate stockout risk.", model=model)


def gateway(
    client: StubGroqClient,
    *,
    retry_policy: RetryPolicy | None = None,
    circuit: CircuitBreaker | None = None,
    sleep=None,
    jitter=None,
) -> LLMGateway:
    kwargs = {}
    if sleep is not None:
        kwargs["sleep"] = sleep
    if jitter is not None:
        kwargs["jitter"] = jitter
    return LLMGateway(
        client=client,
        primary_model="openai/gpt-oss-120b",
        fallback_model="qwen/qwen3.8-27b",
        retry_policy=retry_policy or RetryPolicy(max_attempts=1),
        primary_circuit=circuit,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_primary_model_is_used_when_it_succeeds() -> None:
    client = StubGroqClient([result("openai/gpt-oss-120b")])
    llm_gateway = gateway(client)

    response = await llm_gateway.generate(request())

    assert response.model == "openai/gpt-oss-120b"
    assert response.used_fallback is False
    assert client.calls == ["openai/gpt-oss-120b"]


@pytest.mark.asyncio
async def test_retryable_primary_failure_uses_fallback() -> None:
    client = StubGroqClient(
        [
            LLMProviderError(
                "rate limited",
                model="openai/gpt-oss-120b",
                retryable=True,
                status_code=429,
            ),
            result("qwen/qwen3.8-27b"),
        ]
    )
    llm_gateway = gateway(client)

    response = await llm_gateway.generate(request())

    assert response.used_fallback is True
    assert client.calls == ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]


@pytest.mark.asyncio
async def test_authentication_failure_does_not_call_fallback() -> None:
    client = StubGroqClient(
        [
            LLMProviderError(
                "unauthorized",
                model="openai/gpt-oss-120b",
                retryable=False,
                status_code=401,
            )
        ]
    )
    llm_gateway = gateway(client)

    with pytest.raises(LLMProviderError):
        await llm_gateway.generate(request())

    assert client.calls == ["openai/gpt-oss-120b"]


@pytest.mark.asyncio
async def test_both_model_failures_raise_gateway_error() -> None:
    client = StubGroqClient(
        [
            LLMProviderError(
                "primary unavailable",
                model="openai/gpt-oss-120b",
                retryable=True,
                status_code=503,
            ),
            LLMProviderError(
                "fallback unavailable",
                model="qwen/qwen3.8-27b",
                retryable=True,
                status_code=503,
            ),
        ]
    )
    llm_gateway = gateway(client)

    with pytest.raises(AllModelsFailedError):
        await llm_gateway.generate(request())

    assert client.calls == ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]


def test_gateway_rejects_identical_models() -> None:
    client = StubGroqClient([])

    with pytest.raises(ValueError, match="must be different"):
        LLMGateway(client=client, primary_model="same", fallback_model="same")


@pytest.mark.asyncio
async def test_primary_retries_before_succeeding() -> None:
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    client = StubGroqClient(
        [
            LLMProviderError(
                "temporary outage",
                model="openai/gpt-oss-120b",
                retryable=True,
                status_code=503,
            ),
            result("openai/gpt-oss-120b"),
        ]
    )
    llm_gateway = gateway(
        client,
        retry_policy=RetryPolicy(
            max_attempts=3,
            base_delay_seconds=0.5,
            max_delay_seconds=2,
            jitter_ratio=0.2,
        ),
        sleep=record_sleep,
        jitter=lambda: 0.5,
    )

    response = await llm_gateway.generate(request())

    assert response.attempt_count == 2
    assert response.used_fallback is False
    assert delays == [0.55]
    assert client.calls == ["openai/gpt-oss-120b", "openai/gpt-oss-120b"]


@pytest.mark.asyncio
async def test_primary_exhausts_retries_before_fallback() -> None:
    async def no_wait(_: float) -> None:
        return None

    primary_error = LLMProviderError(
        "rate limited",
        model="openai/gpt-oss-120b",
        retryable=True,
        status_code=429,
    )
    client = StubGroqClient(
        [primary_error, primary_error, result("qwen/qwen3.8-27b")]
    )
    llm_gateway = gateway(
        client,
        retry_policy=RetryPolicy(max_attempts=2, jitter_ratio=0),
        sleep=no_wait,
    )

    response = await llm_gateway.generate(request())

    assert response.used_fallback is True
    assert response.attempt_count == 1
    assert client.calls == [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-120b",
        "qwen/qwen3.8-27b",
    ]


@pytest.mark.asyncio
async def test_open_circuit_skips_primary_until_recovery_window() -> None:
    now = [100.0]
    circuit = CircuitBreaker(
        failure_threshold=1,
        recovery_seconds=30,
        clock=lambda: now[0],
    )
    primary_error = LLMProviderError(
        "primary unavailable",
        model="openai/gpt-oss-120b",
        retryable=True,
        status_code=503,
    )
    client = StubGroqClient(
        [
            primary_error,
            result("qwen/qwen3.8-27b"),
            result("qwen/qwen3.8-27b"),
        ]
    )
    llm_gateway = gateway(client, circuit=circuit)

    first = await llm_gateway.generate(request())
    second = await llm_gateway.generate(request())

    assert first.used_fallback is True
    assert second.used_fallback is True
    assert circuit.state is CircuitState.OPEN
    assert client.calls == [
        "openai/gpt-oss-120b",
        "qwen/qwen3.8-27b",
        "qwen/qwen3.8-27b",
    ]


@pytest.mark.asyncio
async def test_successful_half_open_probe_closes_circuit() -> None:
    now = [100.0]
    circuit = CircuitBreaker(
        failure_threshold=1,
        recovery_seconds=30,
        clock=lambda: now[0],
    )
    primary_error = LLMProviderError(
        "primary unavailable",
        model="openai/gpt-oss-120b",
        retryable=True,
        status_code=503,
    )
    client = StubGroqClient(
        [
            primary_error,
            result("qwen/qwen3.8-27b"),
            result("openai/gpt-oss-120b"),
        ]
    )
    llm_gateway = gateway(client, circuit=circuit)

    await llm_gateway.generate(request())
    now[0] = 131.0
    recovered = await llm_gateway.generate(request())

    assert recovered.used_fallback is False
    assert circuit.state is CircuitState.CLOSED
    assert circuit.failure_count == 0


@pytest.mark.asyncio
async def test_nonretryable_half_open_probe_does_not_leave_probe_stuck() -> None:
    now = [100.0]
    circuit = CircuitBreaker(
        failure_threshold=1,
        recovery_seconds=30,
        clock=lambda: now[0],
    )
    retryable_error = LLMProviderError(
        "primary unavailable",
        model="openai/gpt-oss-120b",
        retryable=True,
        status_code=503,
    )
    auth_error = LLMProviderError(
        "unauthorized",
        model="openai/gpt-oss-120b",
        retryable=False,
        status_code=401,
    )
    client = StubGroqClient(
        [retryable_error, result("qwen/qwen3.8-27b"), auth_error]
    )
    llm_gateway = gateway(client, circuit=circuit)

    await llm_gateway.generate(request())
    now[0] = 131.0

    with pytest.raises(LLMProviderError):
        await llm_gateway.generate(request())

    assert circuit.state is CircuitState.OPEN
