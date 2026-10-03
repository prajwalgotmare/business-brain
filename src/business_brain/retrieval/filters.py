"""Authorization filters that must accompany every document query."""

from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from business_brain.security.context import UserRole

ROLE_SENSITIVITIES: dict[UserRole, tuple[str, ...]] = {
    UserRole.FOUNDER_CFO: ("public", "support", "operations", "accounting", "executive"),
    UserRole.LOGISTICS_MANAGER: ("public", "support", "operations"),
    UserRole.STAFF_ACCOUNTANT: ("public", "accounting"),
    UserRole.SUPPORT_INTERN: ("public", "support"),
}


def governed_document_filter(tenant_id: str, role: UserRole) -> Filter:
    """Build the mandatory tenant and role-sensitivity Qdrant filter."""
    if not tenant_id.strip():
        raise ValueError("tenant_id is required")
    return Filter(
        must=[
            FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
            FieldCondition(
                key="sensitivity", match=MatchAny(any=list(ROLE_SENSITIVITIES[role]))
            ),
        ]
    )
