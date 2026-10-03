"""Authorization filters that must accompany every document query."""

from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from business_brain.security.context import UserRole
from business_brain.security.policy import ROLE_SENSITIVITIES, sensitivities_for

__all__ = ["ROLE_SENSITIVITIES", "governed_document_filter"]


def governed_document_filter(tenant_id: str, role: UserRole) -> Filter:
    """Build the mandatory tenant and role-sensitivity Qdrant filter."""
    if not tenant_id.strip():
        raise ValueError("tenant_id is required")
    return Filter(
        must=[
            FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
            FieldCondition(
                key="sensitivity", match=MatchAny(any=sorted(sensitivities_for(role)))
            ),
        ]
    )
