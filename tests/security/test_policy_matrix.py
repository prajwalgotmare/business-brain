import pytest
from pydantic import ValidationError

from business_brain.security.context import AuthContext, UserRole
from business_brain.security.policy import (
    ALL_ROLES,
    CAPABILITY_ROLES,
    ROLE_SENSITIVITIES,
    AuthorizationDeniedError,
    Capability,
    require_capability,
)

CFO = UserRole.FOUNDER_CFO
LOGISTICS = UserRole.LOGISTICS_MANAGER
ACCOUNTANT = UserRole.STAFF_ACCOUNTANT
SUPPORT = UserRole.SUPPORT_INTERN

EXPECTED_ROLES = {
    Capability.BASIC_ASSISTANT: ALL_ROLES,
    Capability.DOCUMENT_SEARCH: ALL_ROLES,
    Capability.DOCUMENT_SUPPLIER_TERMS: frozenset({CFO}),
    Capability.ANALYTICS_STOCKOUT: frozenset({CFO, LOGISTICS}),
    Capability.ANALYTICS_FREIGHT: frozenset({CFO, ACCOUNTANT}),
    Capability.ANALYTICS_OVERDUE_INVOICES: frozenset({CFO, ACCOUNTANT}),
    Capability.ANALYTICS_MARGIN: frozenset({CFO}),
    Capability.UPLOAD_TRACKING_EVENTS: frozenset({CFO, LOGISTICS}),
    Capability.UPLOAD_VENDOR_INVOICES: frozenset({CFO, ACCOUNTANT}),
    Capability.UPLOAD_DOCUMENT: frozenset({CFO, LOGISTICS, ACCOUNTANT}),
    Capability.DRAFT_PURCHASE_ORDER: frozenset({CFO, LOGISTICS}),
    Capability.DRAFT_CARRIER_DISPUTE: frozenset({CFO, ACCOUNTANT}),
    Capability.DRAFT_PAYMENT_REMINDER: frozenset({CFO, ACCOUNTANT}),
    Capability.DRAFT_DELAY_ADVISORY: frozenset({CFO, LOGISTICS, SUPPORT}),
}


def auth(role: UserRole) -> AuthContext:
    return AuthContext(tenant_id="tenant_aura", user_id="policy-test", role=role)


def test_every_capability_has_one_exact_fail_closed_role_set() -> None:
    assert set(CAPABILITY_ROLES) == set(Capability)
    assert CAPABILITY_ROLES == EXPECTED_ROLES
    assert all(roles for roles in CAPABILITY_ROLES.values())


@pytest.mark.parametrize("capability", list(Capability))
def test_runtime_enforcement_matches_matrix(capability: Capability) -> None:
    for role in UserRole:
        if role in EXPECTED_ROLES[capability]:
            require_capability(auth(role), capability)
        else:
            with pytest.raises(AuthorizationDeniedError):
                require_capability(auth(role), capability)


def test_sensitivity_policy_prevents_financial_and_executive_leakage() -> None:
    assert {
        CFO: frozenset({"public", "support", "operations", "accounting", "executive"}),
        LOGISTICS: frozenset({"public", "support", "operations"}),
        ACCOUNTANT: frozenset({"public", "accounting"}),
        SUPPORT: frozenset({"public", "support"}),
    } == ROLE_SENSITIVITIES


@pytest.mark.parametrize("tenant_id", ["", "AURA", "tenant aura", "_tenant", "../apex"])
def test_auth_context_rejects_invalid_tenant_boundaries(tenant_id: str) -> None:
    with pytest.raises(ValidationError):
        AuthContext(tenant_id=tenant_id, user_id="user", role=CFO)
