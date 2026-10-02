from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from business_brain.core.config import get_settings

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    environment: str
    auth_mode: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        service=settings.app_name,
        environment=settings.app_env,
        auth_mode=settings.auth_mode,
    )

