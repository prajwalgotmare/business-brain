from fastapi.testclient import TestClient

from business_brain.api.dependencies import get_hybrid_retriever
from business_brain.main import app
from business_brain.retrieval.schemas import (
    DocumentCitation,
    HybridSearchResult,
    RetrievalHit,
)


class StubRetriever:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def search(self, query, auth, *, limit=None):
        self.calls.append((query, auth, limit))
        if self.fail:
            raise RuntimeError("Qdrant secret detail")
        return HybridSearchResult(
            query=query,
            tenant_id=auth.tenant_id,
            role=auth.role.value,
            candidate_count=1,
            hits=[
                RetrievalHit(
                    chunk_id="chk_doc_001",
                    content="The contracted credit rate is 10 percent.",
                    sensitivity="accounting",
                    fusion_score=0.7,
                    rerank_score=0.9,
                    citation=DocumentCitation(
                        document_id="doc_aur_fedex_msa",
                        title="Parcel Carrier Master Service Agreement",
                        page_number=1,
                        clause_id="clause_sla_credit_4_2",
                        section_heading="4.2 Late Delivery Credit",
                        chunk_id="chk_doc_001",
                    ),
                )
            ],
        )


HEADERS = {
    "X-Tenant-ID": "tenant_aura",
    "X-User-ID": "demo-accountant",
    "X-Role": "staff_accountant",
}


def test_search_endpoint_accepts_canonical_tenant_and_returns_citations() -> None:
    retriever = StubRetriever()
    app.dependency_overrides[get_hybrid_retriever] = lambda: retriever
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/retrieval/search",
                headers=HEADERS,
                json={"query": "What is the late-delivery credit?", "limit": 3},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == "tenant_aura"
    assert body["hits"][0]["citation"]["clause_id"] == "clause_sla_credit_4_2"
    assert retriever.calls[0][1].tenant_id == "tenant_aura"


def test_search_failure_is_sanitized() -> None:
    app.dependency_overrides[get_hybrid_retriever] = lambda: StubRetriever(fail=True)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/retrieval/search",
                headers=HEADERS,
                json={"query": "What is the late-delivery credit?"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "retrieval_service_unavailable"
    assert "secret detail" not in response.text
