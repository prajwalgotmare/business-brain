from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from business_brain.api.dependencies import get_generation_tracer
from business_brain.api.errors import (
    AnalyticsBadRequestError,
    AnalyticsForbiddenError,
    AnalyticsServiceUnavailableError,
    ErrorDetail,
    ErrorResponse,
    LLMServiceUnavailableError,
    RetrievalServiceUnavailableError,
)
from business_brain.api.request_context import request_id_from_header
from business_brain.api.routes.analytics import router as analytics_router
from business_brain.api.routes.ask import router as ask_router
from business_brain.api.routes.health import router as health_router
from business_brain.api.routes.search import router as search_router
from business_brain.core.config import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_settings()
    yield
    get_generation_tracer().flush()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Governed operations agent for the Aura Brands demo tenant.",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = request_id_from_header(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        details = [
            {
                "location": list(error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        payload = ErrorResponse(
            error=ErrorDetail(
                code="validation_error",
                message="Request validation failed",
                request_id=request.state.request_id,
                details=details,
            )
        )
        return JSONResponse(status_code=422, content=payload.model_dump(mode="json"))

    @app.exception_handler(LLMServiceUnavailableError)
    async def llm_unavailable_handler(
        request: Request,
        _: LLMServiceUnavailableError,
    ) -> JSONResponse:
        payload = ErrorResponse(
            error=ErrorDetail(
                code="llm_service_unavailable",
                message="The AI service is temporarily unavailable. Please try again later.",
                request_id=request.state.request_id,
            )
        )
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))

    @app.exception_handler(RetrievalServiceUnavailableError)
    async def retrieval_unavailable_handler(
        request: Request,
        _: RetrievalServiceUnavailableError,
    ) -> JSONResponse:
        payload = ErrorResponse(
            error=ErrorDetail(
                code="retrieval_service_unavailable",
                message="Document retrieval is temporarily unavailable. Please try again later.",
                request_id=request.state.request_id,
            )
        )
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))

    @app.exception_handler(AnalyticsServiceUnavailableError)
    async def analytics_unavailable_handler(
        request: Request,
        _: AnalyticsServiceUnavailableError,
    ) -> JSONResponse:
        payload = ErrorResponse(
            error=ErrorDetail(
                code="analytics_service_unavailable",
                message="Business analytics are temporarily unavailable. Please try again later.",
                request_id=request.state.request_id,
            )
        )
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))

    @app.exception_handler(AnalyticsForbiddenError)
    async def analytics_forbidden_handler(
        request: Request,
        _: AnalyticsForbiddenError,
    ) -> JSONResponse:
        payload = ErrorResponse(
            error=ErrorDetail(
                code="analytics_forbidden",
                message="Your role cannot access the requested analytic.",
                request_id=request.state.request_id,
            )
        )
        return JSONResponse(status_code=403, content=payload.model_dump(mode="json"))

    @app.exception_handler(AnalyticsBadRequestError)
    async def analytics_bad_request_handler(
        request: Request,
        _: AnalyticsBadRequestError,
    ) -> JSONResponse:
        payload = ErrorResponse(
            error=ErrorDetail(
                code="analytics_bad_request",
                message="The analytics parameters are invalid.",
                request_id=request.state.request_id,
            )
        )
        return JSONResponse(status_code=400, content=payload.model_dump(mode="json"))

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(ask_router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1/retrieval")
    app.include_router(analytics_router, prefix="/api/v1/analytics")
    return app


app = create_app()
