from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class AccountResponse(BaseModel):
    id: UUID
    user_id: UUID
    balance: Decimal = Field(..., ge=0, decimal_places=2)
    currency: str = Field(default="USD", pattern="^USD$")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BalanceResponse(BaseModel):
    balance: Decimal = Field(..., ge=0, decimal_places=2)
    currency: str
    account_id: UUID
    as_of: datetime = Field(default_factory=datetime.utcnow)
