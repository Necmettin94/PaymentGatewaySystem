from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from app.core.enums import TransactionStatus, TransactionType
from app.infrastructure.models.transaction import Transaction
from app.infrastructure.repositories.base import BaseRepository


class TransactionRepository(BaseRepository[Transaction]):
    def __init__(self, db: Session):
        super().__init__(Transaction, db)

    def get_by_account_id(
        self,
        account_id: UUID,
        skip: int = 0,
        limit: int = 20,
        transaction_type: TransactionType | None = None,
        status: TransactionStatus | None = None,
    ) -> list[Transaction]:
        query = (
            self.db.query(Transaction)
            .options(joinedload(Transaction.account))
            .filter(Transaction.account_id == account_id)
            .order_by(desc(Transaction.created_at))
        )

        if transaction_type:
            query = query.filter(Transaction.transaction_type == transaction_type)

        if status:
            query = query.filter(Transaction.status == status)

        return query.offset(skip).limit(limit).all()
