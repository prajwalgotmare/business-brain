from business_brain.llm.groq_client import GroqChatClient, LLMProviderError
from business_brain.llm.reliability import (
    CircuitBreaker,
    CircuitOpenError,
    JitterSource,
    RetryPolicy,
    Sleep,
    default_jitter,
    default_sleep,
)
from business_brain.llm.schemas import GenerationRequest, GenerationResult


class AllModelsFailedError(RuntimeError):
    """Raised when both the primary and fallback models fail."""


class LLMGateway:
    def __init__(
        self,
        *,
        client: GroqChatClient,
        primary_model: str,
        fallback_model: str,
        retry_policy: RetryPolicy | None = None,
        primary_circuit: CircuitBreaker | None = None,
        sleep: Sleep = default_sleep,
        jitter: JitterSource = default_jitter,
    ) -> None:
        if primary_model == fallback_model:
            raise ValueError("Primary and fallback models must be different")
        self._client = client
        self._primary_model = primary_model
        self._fallback_model = fallback_model
        self._retry_policy = retry_policy or RetryPolicy()
        self._primary_circuit = primary_circuit or CircuitBreaker()
        self._sleep = sleep
        self._jitter = jitter

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        try:
            await self._primary_circuit.allow_request()
        except CircuitOpenError:
            return await self._generate_fallback(request)

        try:
            result = await self._generate_with_retry(self._primary_model, request)
        except LLMProviderError as primary_error:
            if not primary_error.retryable:
                await self._primary_circuit.reject_recovery_probe()
                raise
            await self._primary_circuit.record_failure()
            return await self._generate_fallback(request)

        await self._primary_circuit.record_success()
        return result

    async def _generate_fallback(self, request: GenerationRequest) -> GenerationResult:
        try:
            result = await self._generate_with_retry(self._fallback_model, request)
        except LLMProviderError as fallback_error:
            raise AllModelsFailedError(
                "Both Groq models failed; no completion was produced"
            ) from fallback_error

        return result.model_copy(update={"used_fallback": True})

    async def _generate_with_retry(
        self,
        model: str,
        request: GenerationRequest,
    ) -> GenerationResult:
        for attempt in range(1, self._retry_policy.max_attempts + 1):
            try:
                result = await self._client.generate(model, request)
            except LLMProviderError as error:
                is_final_attempt = attempt == self._retry_policy.max_attempts
                if not error.retryable or is_final_attempt:
                    raise

                delay = self._retry_policy.delay_for_retry(attempt, self._jitter())
                await self._sleep(delay)
            else:
                return result.model_copy(update={"attempt_count": attempt})

        raise AssertionError("Retry loop exited without returning or raising")
