from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from business_brain.api.dependencies import get_auth_context
from business_brain.security.context import AuthContext, UserRole

router = APIRouter(prefix="/auth", tags=["auth"])


class CurrentIdentityResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: str
    user_id: str
    role: UserRole


@router.get("/me", response_model=CurrentIdentityResponse)
async def current_identity(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> CurrentIdentityResponse:
    return CurrentIdentityResponse(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        role=auth.role,
    )
