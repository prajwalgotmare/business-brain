from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class UserRole(StrEnum):
    FOUNDER_CFO = "founder_cfo"
    LOGISTICS_MANAGER = "logistics_manager"
    STAFF_ACCOUNTANT = "staff_accountant"
    SUPPORT_INTERN = "support_intern"


class AuthContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: str
    user_id: str
    role: UserRole

