from typing import Any, Literal

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    error: ErrorDetail


class LLMServiceUnavailableError(RuntimeError):
    """Safe application-level error for unavailable model generation."""


class RetrievalServiceUnavailableError(RuntimeError):
    """Safe application-level error for unavailable governed retrieval."""


class AnalyticsServiceUnavailableError(RuntimeError):
    """Safe application-level error for unavailable governed analytics."""


class AnalyticsForbiddenError(PermissionError):
    """Safe application-level error for a role denied access to an analytic."""


class AnalyticsBadRequestError(ValueError):
    """Safe application-level error for invalid analytic parameters."""

