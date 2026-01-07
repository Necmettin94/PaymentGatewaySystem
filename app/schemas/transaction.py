from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import TransactionStatus, TransactionType


class TransactionBase(BaseModel):
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    currency: str = Field(default="USD", pattern="^USD$")


class DepositCreate(TransactionBase):
    pass


class WithdrawalCreate(TransactionBase):
    pass


class TransactionResponse(TransactionBase):
    id: UUID
    account_id: UUID
    transaction_type: TransactionType
    status: TransactionStatus
    bank_transaction_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DepositResponse(TransactionResponse):
    message: str = "Deposit request accepted and is being processed"


class WithdrawalResponse(TransactionResponse):
    message: str = "Withdrawal request accepted and is being processed"
