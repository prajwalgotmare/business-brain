from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from business_brain.api.dependencies import get_auth_context
from business_brain.core.config import Settings, get_settings
from business_brain.security.context import AuthContext, UserRole

router = APIRouter(prefix="/auth", tags=["auth"])


class CurrentIdentityResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: str
    user_id: str
    role: UserRole


class DemoPersonaResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: str
    user_id: str
    role: UserRole
    label: str


_DEMO_PERSONAS = (
    DemoPersonaResponse(
        tenant_id="tenant_aura",
        user_id="demo-founder-cfo",
        role=UserRole.FOUNDER_CFO,
        label="Founder / CFO",
    ),
    DemoPersonaResponse(
        tenant_id="tenant_aura",
        user_id="demo-logistics-manager",
        role=UserRole.LOGISTICS_MANAGER,
        label="Logistics Manager",
    ),
    DemoPersonaResponse(
        tenant_id="tenant_aura",
        user_id="demo-staff-accountant",
        role=UserRole.STAFF_ACCOUNTANT,
        label="Staff Accountant",
    ),
    DemoPersonaResponse(
        tenant_id="tenant_aura",
        user_id="demo-support-intern",
        role=UserRole.SUPPORT_INTERN,
        label="Support Intern",
    ),
)


@router.get("/demo-personas", response_model=list[DemoPersonaResponse])
async def demo_personas(
    _auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[DemoPersonaResponse]:
    if settings.auth_mode != "mock" or settings.app_env == "production":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo personas are unavailable",
        )
    return list(_DEMO_PERSONAS)


@router.get("/me", response_model=CurrentIdentityResponse)
async def current_identity(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> CurrentIdentityResponse:
    return CurrentIdentityResponse(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        role=auth.role,
    )
