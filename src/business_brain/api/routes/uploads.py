from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Path, UploadFile, status
from starlette.concurrency import run_in_threadpool

from business_brain.api.dependencies import get_auth_context, get_upload_service
from business_brain.api.errors import (
    UploadConflictError as ApiUploadConflictError,
)
from business_brain.api.errors import (
    UploadForbiddenError,
    UploadServiceUnavailableError,
)
from business_brain.api.errors import (
    UploadNotFoundError as ApiUploadNotFoundError,
)
from business_brain.security.context import AuthContext
from business_brain.uploads.schemas import (
    UploadCommitResult,
    UploadPreviewResult,
    UploadResourceType,
)
from business_brain.uploads.service import (
    UploadAccessDeniedError,
    UploadConflictError,
    UploadNotFoundError,
    UploadService,
)

router = APIRouter(tags=["uploads"])

UploadId = Annotated[
    str,
    Path(pattern=r"^[0-9a-f]{8}-[0-9a-f-]{27}$", min_length=36, max_length=36),
]


def _safe_upload_error(exc: Exception) -> Exception:
    if isinstance(exc, UploadAccessDeniedError):
        return UploadForbiddenError("Upload access denied")
    if isinstance(exc, UploadNotFoundError):
        return ApiUploadNotFoundError("Upload not found")
    if isinstance(exc, UploadConflictError):
        return ApiUploadConflictError("Upload cannot be committed")
    return UploadServiceUnavailableError("Upload service is temporarily unavailable")


@router.post(
    "/preview",
    response_model=UploadPreviewResult,
    status_code=status.HTTP_201_CREATED,
)
async def preview_upload(
    resource_type: Annotated[UploadResourceType, Form()],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    service: Annotated[UploadService, Depends(get_upload_service)],
    file: Annotated[UploadFile, File()],
    sensitivity: Annotated[str | None, Form()] = None,
    title: Annotated[str | None, Form()] = None,
) -> UploadPreviewResult:
    content = await file.read(service.settings.upload_max_bytes + 1)
    try:
        job = await run_in_threadpool(
            partial(
                service.preview,
                auth=auth,
                resource_type=resource_type,
                filename=file.filename or "",
                media_type=file.content_type,
                content=content,
                sensitivity=sensitivity,
                title=title,
            )
        )
    except Exception as exc:
        raise _safe_upload_error(exc) from exc
    return UploadPreviewResult(job=job)


@router.get("/{upload_id}", response_model=UploadPreviewResult)
def get_upload(
    upload_id: UploadId,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    service: Annotated[UploadService, Depends(get_upload_service)],
) -> UploadPreviewResult:
    try:
        return UploadPreviewResult(job=service.get(auth, upload_id))
    except Exception as exc:
        raise _safe_upload_error(exc) from exc


@router.post("/{upload_id}/commit", response_model=UploadCommitResult)
def commit_upload(
    upload_id: UploadId,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    service: Annotated[UploadService, Depends(get_upload_service)],
) -> UploadCommitResult:
    try:
        return service.commit(auth, upload_id)
    except Exception as exc:
        raise _safe_upload_error(exc) from exc
