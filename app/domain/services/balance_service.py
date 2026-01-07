from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.exceptions import AccountNotFoundError
from app.infrastructure.repositories.account_repository import AccountRepository
from app.infrastructure.repositories.transaction_repository import TransactionRepository

logger = get_logger(__name__)


class BalanceService:
    def __init__(self, db: Session):
        self.db = db
        self.account_repo = AccountRepository(db)
        self.transaction_repo = TransactionRepository(db)

    def get_balance(self, account_id: UUID) -> Decimal:
        # import pdb; pdb.set_trace()
        account = self.account_repo.get_by_id(account_id)
        if not account:
            raise AccountNotFoundError(f"Account {account_id} not found")

        logger.info(
            "balance_queried",
            account_id=str(account_id),
            balance=str(account.balance),
        )

        return Decimal(str(account.balance))

    def get_balance_by_user_id(self, user_id: UUID) -> dict[str, Any]:
        account = self.account_repo.get_by_user_id(user_id)
        if not account:
            raise AccountNotFoundError(f"No account found for user {user_id}")

        return {
            "account_id": account.id,
            "balance": account.balance,
            "currency": account.currency,
        }
