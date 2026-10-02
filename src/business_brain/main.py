from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from business_brain.api.routes.health import router as health_router
from business_brain.core.config import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_settings()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Governed operations agent for the Aura Brands demo tenant.",
        lifespan=lifespan,
    )
    app.include_router(health_router, prefix="/api/v1")
    return app


app = create_app()
