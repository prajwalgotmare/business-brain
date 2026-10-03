"""Governed dense+sparse retrieval with RRF and identifier-aware reranking."""

from __future__ import annotations

import re
from typing import Any

from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import Fusion, FusionQuery, Prefetch, SparseVector

from business_brain.core.config import Settings
from business_brain.retrieval.filters import ROLE_SENSITIVITIES, governed_document_filter
from business_brain.retrieval.qdrant_ingestion import (
    DENSE_VECTOR,
    SPARSE_VECTOR,
    create_client,
)
from business_brain.retrieval.schemas import (
    DocumentCitation,
    HybridSearchResult,
    RetrievalHit,
)
from business_brain.security.context import AuthContext

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[._/-][a-z0-9]+)*", re.IGNORECASE)


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in _TOKEN_PATTERN.findall(value)}


def _rerank_score(query: str, payload: dict[str, Any], fusion_score: float) -> float:
    """Boost exact business identifiers and grounded citation metadata after RRF."""
    query_tokens = _tokens(query)
    searchable = " ".join(
        str(payload.get(field) or "")
        for field in ("content", "title", "section_heading", "clause_id", "document_id")
    )
    searchable_tokens = _tokens(searchable)
    overlap = len(query_tokens & searchable_tokens) / max(len(query_tokens), 1)
    identifier_tokens = {
        token for token in query_tokens if any(char.isdigit() for char in token) or "_" in token
    }
    identifier_overlap = len(identifier_tokens & searchable_tokens) / max(
        len(identifier_tokens), 1
    )
    exact_phrase = float(query.casefold() in searchable.casefold())
    return round(fusion_score + 0.35 * overlap + 0.4 * identifier_overlap + 0.25 * exact_phrase, 8)


def _hit_from_point(query: str, point: Any) -> RetrievalHit:
    payload = dict(point.payload or {})
    required = {
        "chunk_id",
        "content",
        "tenant_id",
        "sensitivity",
        "document_id",
        "title",
        "page_number",
    }
    missing = required - payload.keys()
    if missing:
        raise RuntimeError(f"Qdrant payload is missing fields: {sorted(missing)}")
    fusion_score = float(point.score)
    citation = DocumentCitation(
        document_id=str(payload["document_id"]),
        title=str(payload["title"]),
        page_number=int(payload["page_number"]),
        clause_id=str(payload["clause_id"]) if payload.get("clause_id") else None,
        section_heading=(
            str(payload["section_heading"]) if payload.get("section_heading") else None
        ),
        chunk_id=str(payload["chunk_id"]),
    )
    return RetrievalHit(
        chunk_id=str(payload["chunk_id"]),
        content=str(payload["content"]),
        sensitivity=str(payload["sensitivity"]),
        fusion_score=fusion_score,
        rerank_score=_rerank_score(query, payload, fusion_score),
        citation=citation,
    )


class HybridRetriever:
    def __init__(
        self,
        *,
        settings: Settings,
        client: QdrantClient | None = None,
        dense_model: Any | None = None,
        sparse_model: Any | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or create_client(settings)
        self.dense_model = dense_model or TextEmbedding(model_name=settings.qdrant_dense_model)
        self.sparse_model = sparse_model or SparseTextEmbedding(
            model_name=settings.qdrant_sparse_model
        )

    def search(
        self, query: str, auth: AuthContext, *, limit: int | None = None
    ) -> HybridSearchResult:
        normalized_query = query.strip()
        if len(normalized_query) < 3:
            raise ValueError("query must contain at least three characters")
        result_limit = limit or self.settings.retrieval_result_limit
        if not 1 <= result_limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        candidate_limit = max(self.settings.retrieval_candidate_limit, result_limit)
        query_filter = governed_document_filter(auth.tenant_id, auth.role)
        dense = next(iter(self.dense_model.query_embed(normalized_query))).tolist()
        sparse = next(iter(self.sparse_model.query_embed(normalized_query)))
        sparse_vector = SparseVector(
            indices=sparse.indices.tolist(), values=sparse.values.tolist()
        )
        response = self.client.query_points(
            collection_name=self.settings.qdrant_collection,
            prefetch=[
                Prefetch(
                    query=dense,
                    using=DENSE_VECTOR,
                    filter=query_filter,
                    limit=candidate_limit,
                ),
                Prefetch(
                    query=sparse_vector,
                    using=SPARSE_VECTOR,
                    filter=query_filter,
                    limit=candidate_limit,
                ),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            query_filter=query_filter,
            limit=candidate_limit,
            with_payload=True,
            with_vectors=False,
        )
        allowed = set(ROLE_SENSITIVITIES[auth.role])
        points = list(response.points)
        for point in points:
            payload = point.payload or {}
            wrong_tenant = payload.get("tenant_id") != auth.tenant_id
            unauthorized_sensitivity = payload.get("sensitivity") not in allowed
            if wrong_tenant or unauthorized_sensitivity:
                raise RuntimeError("Qdrant returned data outside the authorization boundary")
        hits = sorted(
            (_hit_from_point(normalized_query, point) for point in points),
            key=lambda hit: (-hit.rerank_score, hit.chunk_id),
        )[:result_limit]
        return HybridSearchResult(
            query=normalized_query,
            tenant_id=auth.tenant_id,
            role=auth.role.value,
            candidate_count=len(points),
            hits=hits,
        )
