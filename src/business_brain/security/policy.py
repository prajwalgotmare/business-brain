"""Single fail-closed authorization matrix for every governed capability."""

from enum import StrEnum

from business_brain.security.context import AuthContext, UserRole


class Capability(StrEnum):
    BASIC_ASSISTANT = "basic_assistant"
    DOCUMENT_SEARCH = "document_search"
    DOCUMENT_SUPPLIER_TERMS = "document_supplier_terms"
    ANALYTICS_STOCKOUT = "analytics_stockout"
    ANALYTICS_FREIGHT = "analytics_freight"
    ANALYTICS_OVERDUE_INVOICES = "analytics_overdue_invoices"
    ANALYTICS_MARGIN = "analytics_margin"
    UPLOAD_TRACKING_EVENTS = "upload_tracking_events"
    UPLOAD_VENDOR_INVOICES = "upload_vendor_invoices"
    UPLOAD_DOCUMENT = "upload_document"
    DRAFT_PURCHASE_ORDER = "draft_purchase_order"
    DRAFT_CARRIER_DISPUTE = "draft_carrier_dispute"
    DRAFT_PAYMENT_REMINDER = "draft_payment_reminder"
    DRAFT_DELAY_ADVISORY = "draft_delay_advisory"


class AuthorizationDeniedError(PermissionError):
    """Authenticated identity lacks an application capability."""


ALL_ROLES = frozenset(UserRole)

CAPABILITY_ROLES: dict[Capability, frozenset[UserRole]] = {
    Capability.BASIC_ASSISTANT: ALL_ROLES,
    Capability.DOCUMENT_SEARCH: ALL_ROLES,
    Capability.DOCUMENT_SUPPLIER_TERMS: frozenset({UserRole.FOUNDER_CFO}),
    Capability.ANALYTICS_STOCKOUT: frozenset(
        {UserRole.FOUNDER_CFO, UserRole.LOGISTICS_MANAGER}
    ),
    Capability.ANALYTICS_FREIGHT: frozenset(
        {UserRole.FOUNDER_CFO, UserRole.STAFF_ACCOUNTANT}
    ),
    Capability.ANALYTICS_OVERDUE_INVOICES: frozenset(
        {UserRole.FOUNDER_CFO, UserRole.STAFF_ACCOUNTANT}
    ),
    Capability.ANALYTICS_MARGIN: frozenset({UserRole.FOUNDER_CFO}),
    Capability.UPLOAD_TRACKING_EVENTS: frozenset(
        {UserRole.FOUNDER_CFO, UserRole.LOGISTICS_MANAGER}
    ),
    Capability.UPLOAD_VENDOR_INVOICES: frozenset(
        {UserRole.FOUNDER_CFO, UserRole.STAFF_ACCOUNTANT}
    ),
    Capability.UPLOAD_DOCUMENT: frozenset(
        {UserRole.FOUNDER_CFO, UserRole.LOGISTICS_MANAGER, UserRole.STAFF_ACCOUNTANT}
    ),
    Capability.DRAFT_PURCHASE_ORDER: frozenset(
        {UserRole.FOUNDER_CFO, UserRole.LOGISTICS_MANAGER}
    ),
    Capability.DRAFT_CARRIER_DISPUTE: frozenset(
        {UserRole.FOUNDER_CFO, UserRole.STAFF_ACCOUNTANT}
    ),
    Capability.DRAFT_PAYMENT_REMINDER: frozenset(
        {UserRole.FOUNDER_CFO, UserRole.STAFF_ACCOUNTANT}
    ),
    Capability.DRAFT_DELAY_ADVISORY: frozenset(
        {UserRole.FOUNDER_CFO, UserRole.LOGISTICS_MANAGER, UserRole.SUPPORT_INTERN}
    ),
}

ROLE_SENSITIVITIES: dict[UserRole, frozenset[str]] = {
    UserRole.FOUNDER_CFO: frozenset(
        {"public", "support", "operations", "accounting", "executive"}
    ),
    UserRole.LOGISTICS_MANAGER: frozenset({"public", "support", "operations"}),
    UserRole.STAFF_ACCOUNTANT: frozenset({"public", "accounting"}),
    UserRole.SUPPORT_INTERN: frozenset({"public", "support"}),
}


def roles_for(capability: Capability) -> frozenset[UserRole]:
    try:
        return CAPABILITY_ROLES[capability]
    except KeyError as exc:
        raise AuthorizationDeniedError("Capability is not registered") from exc


def role_has_capability(role: UserRole, capability: Capability) -> bool:
    return role in roles_for(capability)


def require_capability(auth: AuthContext, capability: Capability) -> None:
    if not role_has_capability(auth.role, capability):
        raise AuthorizationDeniedError("Authenticated role lacks the required capability")


def sensitivities_for(role: UserRole) -> frozenset[str]:
    try:
        return ROLE_SENSITIVITIES[role]
    except KeyError as exc:
        raise AuthorizationDeniedError("Role has no sensitivity policy") from exc
