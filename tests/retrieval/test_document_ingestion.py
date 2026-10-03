from collections import Counter

import pytest
from qdrant_client.models import MatchAny, MatchValue

from business_brain.core.config import Settings
from business_brain.retrieval.documents import extract_all_chunks, load_ingest_documents
from business_brain.retrieval.filters import ROLE_SENSITIVITIES, governed_document_filter
from business_brain.retrieval.qdrant_ingestion import create_client
from business_brain.security.context import UserRole


def test_manifest_allows_only_synthetic_tenant_documents() -> None:
    documents = load_ingest_documents()
    assert len(documents) == 10
    assert {item["tenant_id"] for item in documents} == {"tenant_aura"}
    assert {item["source_type"] for item in documents} == {"synthetic"}
    assert all("/reference/" not in item["relative_path"] for item in documents)


def test_chunking_is_deterministic_complete_and_clause_aware() -> None:
    first = extract_all_chunks()
    second = extract_all_chunks()
    assert first == second
    assert len(first) == 49
    assert len({chunk.point_id for chunk in first}) == 49
    assert len({chunk.chunk_id for chunk in first}) == 49
    assert all(chunk.content and len(chunk.content) <= 850 for chunk in first)
    assert all(chunk.page_number == 1 for chunk in first)
    assert Counter(chunk.sensitivity for chunk in first) == {
        "accounting": 22,
        "executive": 7,
        "operations": 15,
        "public": 5,
    }
    assert {chunk.clause_id for chunk in first if chunk.clause_id} == {
        "clause_sla_credit_4_2",
        "clause_price_tier_3_1",
        "clause_payment_terms_5_2",
        "clause_late_payment_6_3",
    }


@pytest.mark.parametrize("role", list(UserRole))
def test_governed_filter_always_requires_tenant_and_allowed_sensitivities(
    role: UserRole,
) -> None:
    query_filter = governed_document_filter("tenant_aura", role)
    assert query_filter.must is not None
    tenant, sensitivity = query_filter.must
    assert isinstance(tenant.match, MatchValue)
    assert tenant.match.value == "tenant_aura"
    assert isinstance(sensitivity.match, MatchAny)
    assert set(sensitivity.match.any) == set(ROLE_SENSITIVITIES[role])


def test_empty_tenant_filter_is_rejected() -> None:
    with pytest.raises(ValueError, match="tenant_id is required"):
        governed_document_filter(" ", UserRole.FOUNDER_CFO)


def test_qdrant_credentials_are_required() -> None:
    with pytest.raises(RuntimeError, match="must be configured"):
        create_client(Settings(_env_file=None))
