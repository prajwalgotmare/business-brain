from contextlib import AbstractContextManager
from typing import Any

import pytest

from business_brain.llm.schemas import (
    ChatMessage,
    GenerationRequest,
    GenerationResult,
    TokenUsage,
)
from business_brain.observability.tracing import (
    GenerationTraceContext,
    LangfuseGenerationTracer,
    NoOpGenerationTracer,
)
from business_brain.security.context import UserRole


class FakeObservation:
    def __init__(self, *, fail_update: bool = False) -> None:
        self.fail_update = fail_update
        self.updates: list[dict[str, Any]] = []

    def update(self, **kwargs: Any) -> None:
        if self.fail_update:
            raise RuntimeError("trace update failed")
        self.updates.append(kwargs)


class FakeManager(AbstractContextManager):
    def __init__(self, observation: FakeObservation, *, fail_exit: bool = False) -> None:
        self.observation = observation
        self.fail_exit = fail_exit
        self.exits: list[tuple[Any, Any, Any]] = []

    def __enter__(self) -> FakeObservation:
        return self.observation

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.exits.append((exc_type, exc_value, traceback))
        if self.fail_exit:
            raise RuntimeError("trace exit failed")


class FakeLangfuseClient:
    def __init__(
        self,
        *,
        fail_start: bool = False,
        fail_update: bool = False,
        fail_exit: bool = False,
        fail_flush: bool = False,
    ) -> None:
        self.fail_start = fail_start
        self.fail_flush = fail_flush
        self.observation = FakeObservation(fail_update=fail_update)
        self.manager = FakeManager(self.observation, fail_exit=fail_exit)
        self.starts: list[dict[str, Any]] = []
        self.flush_count = 0

    def start_as_current_observation(self, **kwargs: Any) -> FakeManager:
        if self.fail_start:
            raise RuntimeError("trace start failed")
        self.starts.append(kwargs)
        return self.manager

    def flush(self) -> None:
        self.flush_count += 1
        if self.fail_flush:
            raise RuntimeError("trace flush failed")


def generation_request() -> GenerationRequest:
    return GenerationRequest(
        messages=[
            ChatMessage(role="system", content="System instructions"),
            ChatMessage(role="user", content="Show inventory risk"),
        ]
    )


def generation_result() -> GenerationResult:
    return GenerationResult(
        content="Two SKUs are at risk.",
        model="openai/gpt-oss-120b",
        attempt_count=2,
        usage=TokenUsage(prompt_tokens=30, completion_tokens=10, total_tokens=40),
    )


def trace_context() -> GenerationTraceContext:
    return GenerationTraceContext(
        request_id="request-123",
        thread_id="thread-456",
        tenant_id="aura-brands",
        role=UserRole.FOUNDER_CFO,
    )


@pytest.mark.asyncio
async def test_langfuse_trace_records_safe_context_and_usage() -> None:
    client = FakeLangfuseClient()
    tracer = LangfuseGenerationTracer(client=client, capture_content=True)

    result = await tracer.trace_generation(
        context=trace_context(),
        request=generation_request(),
        primary_model="openai/gpt-oss-120b",
        operation=_successful_operation,
    )

    assert result.content == "Two SKUs are at risk."
    start = client.starts[0]
    assert start["as_type"] == "generation"
    assert start["metadata"]["tenant_id"] == "aura-brands"
    assert start["metadata"]["role"] == "founder_cfo"
    assert "user_id" not in start["metadata"]
    assert start["input"][1]["content"] == "Show inventory risk"

    update = client.observation.updates[0]
    assert update["output"] == "Two SKUs are at risk."
    assert update["metadata"]["attempt_count"] == 2
    assert update["usage_details"] == {
        "prompt_tokens": 30,
        "completion_tokens": 10,
        "total_tokens": 40,
    }


@pytest.mark.asyncio
async def test_content_capture_can_be_disabled() -> None:
    client = FakeLangfuseClient()
    tracer = LangfuseGenerationTracer(client=client, capture_content=False)

    await tracer.trace_generation(
        context=trace_context(),
        request=generation_request(),
        primary_model="openai/gpt-oss-120b",
        operation=_successful_operation,
    )

    assert client.starts[0]["input"] == {"message_count": 2, "input_characters": 38}
    assert client.observation.updates[0]["output"] == {"output_characters": 21}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["start", "update", "exit"])
async def test_tracing_failure_never_repeats_or_breaks_generation(failure: str) -> None:
    client = FakeLangfuseClient(
        fail_start=failure == "start",
        fail_update=failure == "update",
        fail_exit=failure == "exit",
    )
    tracer = LangfuseGenerationTracer(client=client, capture_content=True)
    calls = 0

    async def operation() -> GenerationResult:
        nonlocal calls
        calls += 1
        return generation_result()

    result = await tracer.trace_generation(
        context=trace_context(),
        request=generation_request(),
        primary_model="openai/gpt-oss-120b",
        operation=operation,
    )

    assert result.content == "Two SKUs are at risk."
    assert calls == 1


@pytest.mark.asyncio
async def test_generation_error_is_recorded_and_propagated_once() -> None:
    client = FakeLangfuseClient()
    tracer = LangfuseGenerationTracer(client=client, capture_content=True)
    calls = 0

    async def failing_operation() -> GenerationResult:
        nonlocal calls
        calls += 1
        raise RuntimeError("provider failed")

    with pytest.raises(RuntimeError, match="provider failed"):
        await tracer.trace_generation(
            context=trace_context(),
            request=generation_request(),
            primary_model="openai/gpt-oss-120b",
            operation=failing_operation,
        )

    assert calls == 1
    assert client.observation.updates[0]["level"] == "ERROR"
    assert client.observation.updates[0]["status_message"] == "RuntimeError"


@pytest.mark.asyncio
async def test_noop_tracer_only_executes_operation() -> None:
    tracer = NoOpGenerationTracer()

    result = await tracer.trace_generation(
        context=trace_context(),
        request=generation_request(),
        primary_model="openai/gpt-oss-120b",
        operation=_successful_operation,
    )

    assert result == generation_result()


def test_flush_failure_is_suppressed() -> None:
    client = FakeLangfuseClient(fail_flush=True)
    tracer = LangfuseGenerationTracer(client=client, capture_content=True)

    tracer.flush()

    assert client.flush_count == 1


async def _successful_operation() -> GenerationResult:
    return generation_result()
