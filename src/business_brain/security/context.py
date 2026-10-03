from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class UserRole(StrEnum):
    FOUNDER_CFO = "founder_cfo"
    LOGISTICS_MANAGER = "logistics_manager"
    STAFF_ACCOUNTANT = "staff_accountant"
    SUPPORT_INTERN = "support_intern"


class AuthContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: Annotated[
        str,
        Field(
            min_length=2,
            max_length=63,
            pattern=r"^[a-z0-9][a-z0-9_-]*$",
        ),
    ]
    user_id: Annotated[str, Field(min_length=1, max_length=200)]
    role: UserRole

