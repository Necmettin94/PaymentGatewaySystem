from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.exceptions import InsufficientBalanceError
from app.infrastructure.models.account import Account
from app.infrastructure.repositories.base import BaseRepository


class AccountRepository(BaseRepository[Account]):
    def __init__(self, db: Session):
        super().__init__(Account, db)

    def get_by_user_id(self, user_id: UUID) -> Account | None:
        return self.db.query(Account).filter(Account.user_id == user_id).first()

    def get_by_user_id_with_lock(self, user_id: UUID) -> Account | None:
        return self.db.query(Account).filter(Account.user_id == user_id).with_for_update().first()

    def add_balance(
        self,
        account: Account,
        amount: Decimal,
    ) -> Account:
        if amount <= 0:
            raise ValueError("Amount must be positive")

        account.balance = account.balance + amount
        self.db.flush()
        self.db.refresh(account)
        return account

    def subtract_balance(
        self,
        account: Account,
        amount: Decimal,
    ) -> Account:
        if amount <= 0:
            raise ValueError("Amount must be positive")

        if account.balance < amount:
            raise InsufficientBalanceError(
                f"Insufficient balance. Available: {account.balance}, Required: {amount}"
            )

        account.balance = account.balance - amount
        self.db.flush()
        self.db.refresh(account)
        return account
