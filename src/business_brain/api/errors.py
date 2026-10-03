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


class UploadForbiddenError(PermissionError):
    """Safe application-level error for denied upload access."""


class UploadNotFoundError(KeyError):
    """Safe application-level error for a tenant-scoped missing upload."""


class UploadConflictError(RuntimeError):
    """Safe application-level error for an invalid upload state or commit."""


class UploadServiceUnavailableError(RuntimeError):
    """Safe application-level error for unavailable upload persistence."""


class ApprovalNotFoundError(KeyError):
    """Safe application-level error for a missing tenant-scoped approval."""


class ApprovalForbiddenError(PermissionError):
    """Safe application-level error for an unauthorized approval decision."""


class ApprovalConflictError(RuntimeError):
    """Safe application-level error for an approval that is no longer pending."""

