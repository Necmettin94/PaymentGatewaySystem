from decimal import Decimal
from uuid import UUID

from app.core.enums import TransactionStatus, TransactionType
from app.core.logging import get_logger
from app.core.metrics import (
    account_balance,
    active_transactions,
    failed_transactions_total,
    transaction_amount,
    transactions_total,
)
from app.domain.exceptions import AccountNotFoundError, ConcurrentUpdateError
from app.domain.services.base_transaction_service import BaseTransactionService
from app.infrastructure.cache.distributed_lock import SyncDistributedLock
from app.infrastructure.models.transaction import Transaction

logger = get_logger(__name__)


class DepositService(BaseTransactionService):
    def __init__(self, db, redis=None):
        super().__init__(db)
        self.redis = redis

    def create_pending_deposit(
        self,
        account_id: UUID,
        amount: Decimal,
        currency: str,
        idempotency_key: str | None = None,
        celery_task_id: str | None = None,
    ) -> Transaction:
        account = self.account_repo.get_by_id(account_id)
        if not account:
            raise AccountNotFoundError(f"Account {account_id} not found")

        transaction = Transaction(
            account_id=account_id,
            transaction_type=TransactionType.DEPOSIT,
            amount=amount,
            currency=currency,
            status=TransactionStatus.PENDING,
            idempotency_key=idempotency_key,
            celery_task_id=celery_task_id,
        )

        created = self.transaction_repo.create(transaction)
        self.db.commit()

        transactions_total.labels(type="deposit", status="PENDING").inc()
        transaction_amount.labels(type="deposit").observe(float(amount))
        active_transactions.labels(type="deposit", status="PENDING").inc()

        logger.info(
            "deposit_pending_created",
            transaction_id=str(created.id),
            account_id=str(account_id),
            amount=str(amount),
        )

        return created

    def complete_deposit(
        self,
        transaction_id: UUID,
        bank_transaction_id: str,
        bank_response: str | None = None,
    ) -> Transaction:
        transaction = self._get_transaction_or_raise(transaction_id)
        if self.redis:
            with SyncDistributedLock(
                self.redis, f"account:{transaction.account_id}", ttl=10
            ) as lock:
                if not lock.acquired:

                    raise ConcurrentUpdateError(
                        f"Account {transaction.account_id} is locked by another process"
                    )

                return self._complete_deposit_locked(
                    transaction, bank_transaction_id, bank_response
                )
        else:
            return self._complete_deposit_locked(transaction, bank_transaction_id, bank_response)

    def _complete_deposit_locked(
        self,
        transaction: Transaction,
        bank_transaction_id: str,
        bank_response: str | None,
    ) -> Transaction:
        try:
            account = self.account_repo.get_by_id_with_lock(transaction.account_id)
            if not account:
                raise AccountNotFoundError(f"Account {transaction.account_id} not found")

            self.account_repo.add_balance(account, Decimal(str(transaction.amount)))
            transaction.status = TransactionStatus.SUCCESS
            transaction.bank_transaction_id = bank_transaction_id
            transaction.bank_response = bank_response
            self._update_and_commit(transaction)

            transactions_total.labels(type="deposit", status="SUCCESS").inc()
            active_transactions.labels(type="deposit", status="PENDING").dec()
            account_balance.observe(float(account.balance))

            logger.info(
                "deposit_completed",
                transaction_id=str(transaction.id),
                bank_transaction_id=bank_transaction_id,
                new_balance=str(account.balance),
            )
            self._trigger_webhook_if_configured(transaction, account)

            return transaction

        except Exception as e:
            self.db.rollback()
            logger.error(
                "deposit_completion_failed",
                transaction_id=str(transaction.id),
                error=str(e),
            )
            raise

    def fail_deposit(
        self,
        transaction_id: UUID,
        error_code: str,
        error_message: str,
        bank_response: str | None = None,
    ) -> Transaction:
        transaction = self._get_transaction_or_raise(transaction_id)

        account = self.account_repo.get_by_id(transaction.account_id)
        transaction.status = TransactionStatus.FAILED
        transaction.error_code = error_code
        transaction.error_message = error_message
        transaction.bank_response = bank_response
        self._update_and_commit(transaction)

        transactions_total.labels(type="deposit", status="FAILED").inc()
        active_transactions.labels(type="deposit", status="PENDING").dec()

        failed_transactions_total.labels(type="deposit", error_code=error_code).inc()

        logger.warning(
            "deposit_failed",
            transaction_id=str(transaction_id),
            error_code=error_code,
            error_message=error_message,
        )

        # trigger webhook here
        if account:
            self._trigger_webhook_if_configured(transaction, account)

        return transaction
