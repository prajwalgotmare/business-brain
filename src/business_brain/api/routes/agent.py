from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from business_brain.agent.actions import ActionDraftArtifact
from business_brain.agent.schemas import (
    AgentRoute,
    RiskLevel,
    SupervisorIntent,
    WorkflowStatus,
)
from business_brain.agent.supervisor import GovernedSupervisor
from business_brain.api.dependencies import get_auth_context, get_governed_supervisor
from business_brain.api.request_context import get_request_id
from business_brain.llm.schemas import TokenUsage
from business_brain.retrieval.schemas import DocumentCitation
from business_brain.security.context import AuthContext, UserRole

router = APIRouter(tags=["agent"])


class AgentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=3, max_length=4_000)
    thread_id: UUID | None = None
    max_tokens: int = Field(default=512, ge=64, le=4_096)


class AgentContextResponse(BaseModel):
    tenant_id: str
    role: UserRole


class AgentResponse(BaseModel):
    request_id: str
    thread_id: UUID
    answer: str
    route: AgentRoute
    intent: SupervisorIntent
    risk_level: RiskLevel
    status: WorkflowStatus
    rationale: str
    error_code: str | None
    model: str | None
    provider: str | None
    used_fallback: bool
    attempt_count: int
    supervisor_attempts: int
    usage: TokenUsage
    tool_name: str | None
    tool_result: Any | None
    citations: list[DocumentCitation]
    action_draft: ActionDraftArtifact | None
    context: AgentContextResponse


@router.post("/agent/run", response_model=AgentResponse)
async def run_agent(
    payload: AgentRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    supervisor: Annotated[GovernedSupervisor, Depends(get_governed_supervisor)],
) -> AgentResponse:
    request_id = get_request_id(request)
    thread_id = payload.thread_id or uuid4()
    result = await supervisor.run(
        request_id=request_id,
        thread_id=str(thread_id),
        auth=auth,
        question=payload.question,
        max_tokens=payload.max_tokens,
    )
    return AgentResponse(
        **result.model_dump(exclude={"thread_id"}),
        thread_id=UUID(result.thread_id),
        context=AgentContextResponse(tenant_id=auth.tenant_id, role=auth.role),
    )
