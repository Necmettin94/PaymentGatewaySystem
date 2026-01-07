from uuid import UUID

from sqlalchemy.orm import Session

from app.core.enums import TransactionStatus
from app.core.logging import get_logger
from app.infrastructure.models.transaction import Transaction
from app.infrastructure.repositories.account_repository import AccountRepository
from app.infrastructure.repositories.transaction_repository import TransactionRepository
from app.infrastructure.repositories.user_repository import UserRepository
from app.infrastructure.repositories.webhook_repository import WebhookRepository
from app.workers.tasks.webhook_tasks import send_webhook_notification

logger = get_logger(__name__)


class BaseTransactionService:
    def __init__(self, db: Session):
        self.db = db
        self.account_repo = AccountRepository(db)
        self.transaction_repo = TransactionRepository(db)

    def _get_transaction_or_raise(self, transaction_id: UUID) -> Transaction:
        transaction = self.transaction_repo.get_by_id(transaction_id)
        if not transaction:
            raise ValueError(f"Transaction {transaction_id} not found")
        return transaction

    def _update_and_commit(self, transaction: Transaction) -> Transaction:
        self.transaction_repo.update(transaction)
        self.db.commit()
        return transaction

    def mark_pending_review(
        self,
        transaction_id: UUID,
        reason: str,
        bank_response: str | None = None,
    ) -> Transaction:
        transaction = self._get_transaction_or_raise(transaction_id)

        transaction.status = TransactionStatus.PENDING_REVIEW
        transaction.error_message = reason
        transaction.bank_response = bank_response
        self._update_and_commit(transaction)
        # check here later
        logger.warning(
            "transaction_pending_review",
            transaction_id=str(transaction_id),
            transaction_type=transaction.transaction_type,
            reason=reason,
        )
        return transaction

    def update_status(
        self,
        transaction_id: UUID,
        status: TransactionStatus,
    ) -> Transaction:
        transaction = self._get_transaction_or_raise(transaction_id)
        transaction.status = status
        return self._update_and_commit(transaction)

    def _trigger_webhook_if_configured(self, transaction: Transaction, account) -> None:
        user_repo = UserRepository(self.db)
        user = user_repo.get_by_id(account.user_id)

        if not user or not user.webhook_url:
            return

        webhook_repo = WebhookRepository(self.db)
        payload = {
            "event": (
                "transaction.completed"
                if transaction.status == TransactionStatus.SUCCESS
                else "transaction.failed"
            ),
            "transaction": {
                "id": str(transaction.id),
                "type": transaction.transaction_type,
                "amount": str(transaction.amount),
                "currency": transaction.currency,
                "status": transaction.status,
                "bank_transaction_id": transaction.bank_transaction_id,
                "error_code": transaction.error_code,
                "error_message": transaction.error_message,
                "created_at": (
                    transaction.created_at.isoformat() if transaction.created_at else None
                ),
                "updated_at": (
                    transaction.updated_at.isoformat() if transaction.updated_at else None
                ),
            },
            "account": {
                "id": str(account.id),
                "balance": str(account.balance),
            },
        }
        delivery = webhook_repo.create_delivery(
            transaction_id=transaction.id,
            webhook_url=user.webhook_url,
            payload=payload,
        )
        self.db.commit()
        send_webhook_notification.delay(str(delivery.id))

        logger.info(
            "webhook_queued",
            transaction_id=str(transaction.id),
            delivery_id=str(delivery.id),
            webhook_url=user.webhook_url,
        )
