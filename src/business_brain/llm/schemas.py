from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class GenerationRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float = Field(default=0.1, ge=0, le=2)
    max_tokens: int = Field(default=1_024, ge=1, le=8_192)
    response_format: Literal["text", "json_object"] = "text"


class TokenUsage(BaseModel):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class GenerationResult(BaseModel):
    content: str
    model: str
    provider: Literal["groq"] = "groq"
    used_fallback: bool = False
    attempt_count: int = Field(default=1, ge=1)
    finish_reason: str | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
