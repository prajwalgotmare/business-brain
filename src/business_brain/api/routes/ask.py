from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from business_brain.api.dependencies import get_auth_context, get_llm_gateway
from business_brain.api.errors import LLMServiceUnavailableError
from business_brain.api.request_context import get_request_id
from business_brain.llm.gateway import AllModelsFailedError, LLMGateway
from business_brain.llm.groq_client import LLMProviderError
from business_brain.llm.schemas import ChatMessage, GenerationRequest, TokenUsage
from business_brain.security.context import AuthContext, UserRole

router = APIRouter(tags=["assistant"])


class AskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=3, max_length=4_000)
    thread_id: UUID | None = None
    max_tokens: int = Field(default=1_024, ge=64, le=4_096)


class RequestContextResponse(BaseModel):
    tenant_id: str
    role: UserRole


class AskResponse(BaseModel):
    request_id: str
    thread_id: UUID
    answer: str
    model: str
    provider: str
    used_fallback: bool
    attempt_count: int
    usage: TokenUsage
    context: RequestContextResponse


def _system_message(auth: AuthContext) -> ChatMessage:
    return ChatMessage(
        role="system",
        content=(
            "You are Business Brain, a governed enterprise operations assistant. "
            f"The authenticated tenant is {auth.tenant_id} and the user's role is "
            f"{auth.role.value}. Do not claim access to business facts, documents, or "
            "tools that have not been supplied. Clearly state when business data is unavailable."
        ),
    )


@router.post("/ask", response_model=AskResponse)
async def ask(
    payload: AskRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    gateway: Annotated[LLMGateway, Depends(get_llm_gateway)],
) -> AskResponse:
    generation_request = GenerationRequest(
        messages=[
            _system_message(auth),
            ChatMessage(role="user", content=payload.question),
        ],
        max_tokens=payload.max_tokens,
    )

    try:
        result = await gateway.generate(generation_request)
    except (AllModelsFailedError, LLMProviderError) as exc:
        raise LLMServiceUnavailableError("LLM generation is temporarily unavailable") from exc

    return AskResponse(
        request_id=get_request_id(request),
        thread_id=payload.thread_id or uuid4(),
        answer=result.content,
        model=result.model,
        provider=result.provider,
        used_fallback=result.used_fallback,
        attempt_count=result.attempt_count,
        usage=result.usage,
        context=RequestContextResponse(tenant_id=auth.tenant_id, role=auth.role),
    )

