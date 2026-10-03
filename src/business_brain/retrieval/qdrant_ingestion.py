"""Idempotent dense+sparse ingestion into the governed Qdrant collection."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from business_brain.core.config import Settings
from business_brain.retrieval.documents import PROJECT_ROOT, DocumentChunk, extract_all_chunks
from business_brain.retrieval.filters import ROLE_SENSITIVITIES, governed_document_filter
from business_brain.security.context import UserRole

DENSE_VECTOR = "dense"
SPARSE_VECTOR = "bm25"
DENSE_SIZE = 384
INGESTION_MANIFEST = PROJECT_ROOT / "data" / "quality" / "qdrant_ingestion_manifest.json"


@dataclass(frozen=True)
class QdrantIngestionReport:
    collection_name: str
    document_count: int
    point_count: int
    tenant_counts: dict[str, int]
    sensitivity_counts: dict[str, int]
    role_visible_counts: dict[str, int]


def create_client(settings: Settings) -> QdrantClient:
    if not settings.qdrant_url or not settings.qdrant_api_key:
        raise RuntimeError("QDRANT_URL and QDRANT_API_KEY must be configured")
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout=settings.qdrant_timeout_seconds,
    )


def ensure_collection(client: QdrantClient, settings: Settings) -> None:
    if not client.collection_exists(settings.qdrant_collection):
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config={
                DENSE_VECTOR: VectorParams(size=DENSE_SIZE, distance=Distance.COSINE)
            },
            sparse_vectors_config={SPARSE_VECTOR: SparseVectorParams()},
            on_disk_payload=True,
        )
    indexes = {
        "tenant_id": PayloadSchemaType.KEYWORD,
        "sensitivity": PayloadSchemaType.KEYWORD,
        "document_id": PayloadSchemaType.KEYWORD,
        "document_kind": PayloadSchemaType.KEYWORD,
        "clause_id": PayloadSchemaType.KEYWORD,
        "page_number": PayloadSchemaType.INTEGER,
    }
    info = client.get_collection(settings.qdrant_collection)
    for field_name, field_schema in indexes.items():
        if field_name not in info.payload_schema:
            client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name=field_name,
                field_schema=field_schema,
                wait=True,
            )


def _embed_points(settings: Settings, chunks: list[DocumentChunk]) -> list[PointStruct]:
    texts = [chunk.content for chunk in chunks]
    dense_model = TextEmbedding(model_name=settings.qdrant_dense_model)
    sparse_model = SparseTextEmbedding(model_name=settings.qdrant_sparse_model)
    dense_vectors = list(dense_model.embed(texts, batch_size=32))
    sparse_vectors = list(sparse_model.embed(texts, batch_size=32))
    if len(dense_vectors) != len(chunks) or len(sparse_vectors) != len(chunks):
        raise RuntimeError("Embedding count does not match chunk count")
    return [
        PointStruct(
            id=chunk.point_id,
            vector={
                DENSE_VECTOR: dense.tolist(),
                SPARSE_VECTOR: SparseVector(
                    indices=sparse.indices.tolist(), values=sparse.values.tolist()
                ),
            },
            payload=chunk.payload(),
        )
        for chunk, dense, sparse in zip(chunks, dense_vectors, sparse_vectors, strict=True)
    ]


def _document_filter(chunk: DocumentChunk) -> Filter:
    return Filter(
        must=[
            FieldCondition(key="tenant_id", match=MatchValue(value=chunk.tenant_id)),
            FieldCondition(key="document_id", match=MatchValue(value=chunk.document_id)),
        ]
    )


def _sync_points(
    client: QdrantClient, settings: Settings, chunks: list[DocumentChunk], points: list[PointStruct]
) -> None:
    by_document: dict[str, list[PointStruct]] = {}
    first_chunk: dict[str, DocumentChunk] = {}
    for chunk, point in zip(chunks, points, strict=True):
        by_document.setdefault(chunk.document_id, []).append(point)
        first_chunk.setdefault(chunk.document_id, chunk)
    for document_id, document_points in by_document.items():
        selector = FilterSelector(filter=_document_filter(first_chunk[document_id]))
        client.delete(settings.qdrant_collection, points_selector=selector, wait=True)
        client.upsert(settings.qdrant_collection, points=document_points, wait=True)


def _write_manifest(settings: Settings, report: QdrantIngestionReport) -> None:
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "collection_name": report.collection_name,
        "dense_model": settings.qdrant_dense_model,
        "dense_dimensions": DENSE_SIZE,
        "sparse_model": settings.qdrant_sparse_model,
        "document_count": report.document_count,
        "point_count": report.point_count,
        "tenant_counts": report.tenant_counts,
        "sensitivity_counts": report.sensitivity_counts,
        "role_visible_counts": report.role_visible_counts,
    }
    INGESTION_MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def ingest_documents(settings: Settings | None = None) -> QdrantIngestionReport:
    current = settings or Settings()
    chunks = extract_all_chunks()
    points = _embed_points(current, chunks)
    client = create_client(current)
    try:
        ensure_collection(client, current)
        _sync_points(client, current, chunks, points)
        expected = len(chunks)
        actual = client.count(current.qdrant_collection, exact=True).count
        if actual != expected:
            raise RuntimeError(f"Qdrant point-count drift: expected {expected}, found {actual}")
        indexed = client.get_collection(current.qdrant_collection).payload_schema
        required_indexes = {
            "tenant_id", "sensitivity", "document_id", "document_kind", "clause_id", "page_number"
        }
        if not required_indexes.issubset(indexed):
            raise RuntimeError("Required Qdrant payload indexes are missing")
        sensitivity_counts = Counter(chunk.sensitivity for chunk in chunks)
        role_counts: dict[str, int] = {}
        for role in UserRole:
            expected_role_count = sum(
                count
                for sensitivity, count in sensitivity_counts.items()
                if sensitivity in ROLE_SENSITIVITIES[role]
            )
            actual_role_count = client.count(
                current.qdrant_collection,
                count_filter=governed_document_filter("tenant_aura", role),
                exact=True,
            ).count
            if actual_role_count != expected_role_count:
                raise RuntimeError(f"Qdrant role-filter drift for {role.value}")
            role_counts[role.value] = actual_role_count
        apex_count = client.count(
            current.qdrant_collection,
            count_filter=governed_document_filter("tenant_apex", UserRole.FOUNDER_CFO),
            exact=True,
        ).count
        if apex_count != 0:
            raise RuntimeError("Cross-tenant Qdrant isolation check failed")
    finally:
        client.close()
    report = QdrantIngestionReport(
        collection_name=current.qdrant_collection,
        document_count=len({chunk.document_id for chunk in chunks}),
        point_count=len(chunks),
        tenant_counts=dict(sorted(Counter(chunk.tenant_id for chunk in chunks).items())),
        sensitivity_counts=dict(sorted(Counter(chunk.sensitivity for chunk in chunks).items())),
        role_visible_counts=dict(sorted(role_counts.items())),
    )
    _write_manifest(current, report)
    return report
