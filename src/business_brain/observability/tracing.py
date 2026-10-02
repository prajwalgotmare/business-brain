from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from business_brain.llm.schemas import GenerationRequest, GenerationResult
from business_brain.security.context import UserRole

GenerationOperation = Callable[[], Awaitable[GenerationResult]]


@dataclass(frozen=True)
class GenerationTraceContext:
    request_id: str
    thread_id: str
    tenant_id: str
    role: UserRole


class GenerationTracer(Protocol):
    async def trace_generation(
        self,
        *,
        context: GenerationTraceContext,
        request: GenerationRequest,
        primary_model: str,
        operation: GenerationOperation,
    ) -> GenerationResult: ...

    def flush(self) -> None: ...


class NoOpGenerationTracer:
    async def trace_generation(
        self,
        *,
        context: GenerationTraceContext,
        request: GenerationRequest,
        primary_model: str,
        operation: GenerationOperation,
    ) -> GenerationResult:
        del context, request, primary_model
        return await operation()

    def flush(self) -> None:
        return None


class LangfuseGenerationTracer:
    def __init__(self, *, client: Any, capture_content: bool) -> None:
        self._client = client
        self._capture_content = capture_content

    async def trace_generation(
        self,
        *,
        context: GenerationTraceContext,
        request: GenerationRequest,
        primary_model: str,
        operation: GenerationOperation,
    ) -> GenerationResult:
        observation_input = self._input_payload(request)
        metadata = {
            "request_id": context.request_id,
            "thread_id": context.thread_id,
            "tenant_id": context.tenant_id,
            "role": context.role.value,
            "provider": "groq",
            "primary_model": primary_model,
            "capture_content": self._capture_content,
        }

        try:
            manager = self._client.start_as_current_observation(
                as_type="generation",
                name="llm.gateway.generate",
                input=observation_input,
                metadata=metadata,
                model=primary_model,
                model_parameters={
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens,
                },
            )
            observation = manager.__enter__()
        except Exception:
            return await operation()

        try:
            result = await operation()
        except BaseException as operation_error:
            self._safe_update(
                observation,
                level="ERROR",
                status_message=type(operation_error).__name__,
                metadata={**metadata, "outcome": "error"},
            )
            self._safe_exit(manager, operation_error)
            raise

        self._safe_update(
            observation,
            output=self._output_payload(result),
            model=result.model,
            metadata={
                **metadata,
                "outcome": "success",
                "final_model": result.model,
                "used_fallback": result.used_fallback,
                "attempt_count": result.attempt_count,
                "finish_reason": result.finish_reason,
            },
            usage_details={
                "prompt_tokens": result.usage.prompt_tokens,
                "completion_tokens": result.usage.completion_tokens,
                "total_tokens": result.usage.total_tokens,
            },
        )
        self._safe_exit(manager)
        return result

    def flush(self) -> None:
        try:
            self._client.flush()
        except Exception:
            return None

    def _input_payload(self, request: GenerationRequest) -> Any:
        if self._capture_content:
            return [message.model_dump(mode="json") for message in request.messages]
        return {
            "message_count": len(request.messages),
            "input_characters": sum(len(message.content) for message in request.messages),
        }

    def _output_payload(self, result: GenerationResult) -> Any:
        if self._capture_content:
            return result.content
        return {"output_characters": len(result.content)}

    @staticmethod
    def _safe_update(observation: Any, **kwargs: Any) -> None:
        try:
            observation.update(**kwargs)
        except Exception:
            return None

    @staticmethod
    def _safe_exit(manager: Any, error: BaseException | None = None) -> None:
        try:
            if error is None:
                manager.__exit__(None, None, None)
            else:
                manager.__exit__(type(error), error, error.__traceback__)
        except Exception:
            return None

