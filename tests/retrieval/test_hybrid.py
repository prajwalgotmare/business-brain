from types import SimpleNamespace

import numpy as np
import pytest

from business_brain.core.config import Settings
from business_brain.retrieval.hybrid import HybridRetriever, _rerank_score
from business_brain.security.context import AuthContext, UserRole


class FakeDenseModel:
    def query_embed(self, query: str):
        assert query
        yield np.array([0.1, 0.2], dtype=np.float32)


class FakeSparseModel:
    def query_embed(self, query: str):
        assert query
        yield SimpleNamespace(
            indices=np.array([1, 7], dtype=np.uint32),
            values=np.array([0.5, 0.8], dtype=np.float32),
        )


def point(*, chunk_id: str, content: str, sensitivity: str = "accounting"):
    return SimpleNamespace(
        score=0.5,
        payload={
            "chunk_id": chunk_id,
            "content": content,
            "tenant_id": "tenant_aura",
            "sensitivity": sensitivity,
            "document_id": "doc_aur_fedex_msa",
            "title": "Parcel Carrier Master Service Agreement",
            "page_number": 1,
            "section_heading": "4.2 Late Delivery Credit",
            "clause_id": "clause_sla_credit_4_2",
        },
    )


class FakeClient:
    def __init__(self, points):
        self.points = points
        self.calls = []

    def query_points(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(points=self.points)


def retriever(client: FakeClient) -> HybridRetriever:
    return HybridRetriever(
        settings=Settings(
            _env_file=None,
            qdrant_collection="test_documents",
            retrieval_candidate_limit=10,
            retrieval_result_limit=3,
        ),
        client=client,
        dense_model=FakeDenseModel(),
        sparse_model=FakeSparseModel(),
    )


def test_hybrid_search_filters_both_prefetches_and_returns_citation() -> None:
    client = FakeClient(
        [
            point(chunk_id="generic", content="General carrier billing terms."),
            point(
                chunk_id="exact",
                content="Shipment shp_aur_000021 receives a 10 percent late delivery credit.",
            ),
        ]
    )
    auth = AuthContext(
        tenant_id="tenant_aura", user_id="accountant", role=UserRole.STAFF_ACCOUNTANT
    )

    result = retriever(client).search("credit for shp_aur_000021", auth, limit=2)

    assert [hit.chunk_id for hit in result.hits] == ["exact", "generic"]
    assert result.hits[0].citation.page_number == 1
    assert result.hits[0].citation.clause_id == "clause_sla_credit_4_2"
    call = client.calls[0]
    assert len(call["prefetch"]) == 2
    assert all(prefetch.filter is not None for prefetch in call["prefetch"])
    assert call["query_filter"] is not None
    assert call["with_vectors"] is False


def test_post_query_authorization_check_rejects_leaked_payload() -> None:
    leaked = point(chunk_id="leaked", content="Private executive pricing", sensitivity="executive")
    client = FakeClient([leaked])
    auth = AuthContext(
        tenant_id="tenant_aura", user_id="intern", role=UserRole.SUPPORT_INTERN
    )

    with pytest.raises(RuntimeError, match="outside the authorization boundary"):
        retriever(client).search("pricing", auth)


def test_identifier_aware_reranking_boosts_exact_business_ids() -> None:
    generic = {"content": "shipment reconciliation", "title": "Freight invoice"}
    exact = {
        "content": "Reconcile shipment shp_aur_000021 against the carrier invoice.",
        "title": "Freight invoice",
    }
    query = "reconcile shp_aur_000021"
    assert _rerank_score(query, exact, 0.4) > _rerank_score(query, generic, 0.4)


def test_short_query_and_invalid_limit_are_rejected() -> None:
    auth = AuthContext(
        tenant_id="tenant_aura", user_id="cfo", role=UserRole.FOUNDER_CFO
    )
    service = retriever(FakeClient([]))
    with pytest.raises(ValueError, match="three characters"):
        service.search("x", auth)
    with pytest.raises(ValueError, match="between 1 and 20"):
        service.search("valid query", auth, limit=21)
