from typing import Any, Protocol

import httpx

from business_brain.llm.schemas import GenerationRequest, GenerationResult, TokenUsage


class LLMProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        model: str,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.model = model
        self.retryable = retryable
        self.status_code = status_code


class GroqChatClient(Protocol):
    async def generate(self, model: str, request: GenerationRequest) -> GenerationResult: ...


class HttpGroqChatClient:
    def __init__(self, *, api_key: str, base_url: str, timeout_seconds: float) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_seconds)

    async def generate(self, model: str, request: GenerationRequest) -> GenerationResult:
        payload = {
            "model": model,
            "messages": [message.model_dump() for message in request.messages],
            "temperature": request.temperature,
            "max_completion_tokens": request.max_tokens,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise LLMProviderError(
                "Groq request timed out",
                model=model,
                retryable=True,
            ) from exc
        except httpx.NetworkError as exc:
            raise LLMProviderError(
                "Groq network request failed",
                model=model,
                retryable=True,
            ) from exc

        if response.is_error:
            status_code = response.status_code
            retryable = status_code in {404, 408, 409, 425, 429} or status_code >= 500
            raise LLMProviderError(
                f"Groq returned HTTP {status_code}",
                model=model,
                retryable=retryable,
                status_code=status_code,
            )

        return self._parse_response(model=model, payload=response.json())

    @staticmethod
    def _parse_response(model: str, payload: dict[str, Any]) -> GenerationResult:
        try:
            choice = payload["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(
                "Groq returned an invalid completion payload",
                model=model,
                retryable=False,
            ) from exc

        usage = payload.get("usage", {})
        return GenerationResult(
            content=content or "",
            model=payload.get("model", model),
            finish_reason=choice.get("finish_reason"),
            usage=TokenUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
        )

