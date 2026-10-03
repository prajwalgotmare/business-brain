from typing import Annotated

from fastapi import APIRouter, Depends

from business_brain.api.dependencies import get_auth_context, get_hybrid_retriever
from business_brain.api.errors import RetrievalServiceUnavailableError
from business_brain.retrieval.hybrid import HybridRetriever
from business_brain.retrieval.schemas import HybridSearchResult, SearchRequest
from business_brain.security.context import AuthContext

router = APIRouter(tags=["retrieval"])


@router.post("/search", response_model=HybridSearchResult)
def search_documents(
    payload: SearchRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    retriever: Annotated[HybridRetriever, Depends(get_hybrid_retriever)],
) -> HybridSearchResult:
    try:
        return retriever.search(payload.query, auth, limit=payload.limit)
    except Exception as exc:
        raise RetrievalServiceUnavailableError(
            "Document retrieval is temporarily unavailable"
        ) from exc
