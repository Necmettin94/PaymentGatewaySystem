from decimal import Decimal
from uuid import UUID

from app.core.enums import TransactionStatus, TransactionType
from app.core.logging import get_logger
from app.core.metrics import (
    account_balance,
    active_transactions,
    failed_transactions_total,
    insufficient_balance_errors,
    transaction_amount,
    transactions_total,
)
from app.domain.exceptions import (
    AccountNotFoundError,
    ConcurrentUpdateError,
    InsufficientBalanceError,
)
from app.domain.services.base_transaction_service import BaseTransactionService
from app.infrastructure.cache.distributed_lock import SyncDistributedLock
from app.infrastructure.models.transaction import Transaction

logger = get_logger(__name__)


class WithdrawalService(BaseTransactionService):
    def __init__(self, db, redis=None):
        super().__init__(db)
        self.redis = redis

    def create_pending_withdrawal(
        self,
        account_id: UUID,
        amount: Decimal,
        currency: str,
        idempotency_key: str | None = None,
        celery_task_id: str | None = None,
    ) -> Transaction:
        account = self.account_repo.get_by_id_with_lock(
            account_id
        )  # prevent race conditions, best practise? later
        if not account:
            raise AccountNotFoundError(f"Account {account_id} not found")

        if account.balance < amount:
            insufficient_balance_errors.inc()
            logger.warning(
                "withdrawal_insufficient_balance",
                account_id=str(account_id),
                requested_amount=str(amount),
                available_balance=str(account.balance),
            )
            raise InsufficientBalanceError(
                f"Insufficient balance. Available: {account.balance}, Required: {amount}"
            )

        transaction = Transaction(
            account_id=account_id,
            transaction_type=TransactionType.WITHDRAWAL,
            amount=amount,
            currency=currency,
            status=TransactionStatus.PENDING,
            idempotency_key=idempotency_key,
            celery_task_id=celery_task_id,
        )

        created = self.transaction_repo.create(transaction)
        self.db.commit()

        # Update metrics
        transactions_total.labels(type="withdrawal", status="PENDING").inc()
        transaction_amount.labels(type="withdrawal").observe(float(amount))
        active_transactions.labels(type="withdrawal", status="PENDING").inc()

        logger.info(
            "withdrawal_pending_created",
            transaction_id=str(created.id),
            account_id=str(account_id),
            amount=str(amount),
            current_balance=str(account.balance),
        )

        return created

    def complete_withdrawal(
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

                return self._complete_withdrawal_locked(
                    transaction, bank_transaction_id, bank_response
                )
        else:
            # Fallback: DB lock only
            return self._complete_withdrawal_locked(transaction, bank_transaction_id, bank_response)

    def _complete_withdrawal_locked(
        self,
        transaction: Transaction,
        bank_transaction_id: str,
        bank_response: str | None,
    ) -> Transaction:
        try:
            account = self.account_repo.get_by_id_with_lock(transaction.account_id)
            if not account:
                raise AccountNotFoundError(f"Account {transaction.account_id} not found")
            self.account_repo.subtract_balance(account, Decimal(str(transaction.amount)))
            transaction.status = TransactionStatus.SUCCESS
            transaction.bank_transaction_id = bank_transaction_id
            transaction.bank_response = bank_response
            self._update_and_commit(transaction)

            transactions_total.labels(type="withdrawal", status="SUCCESS").inc()
            active_transactions.labels(type="withdrawal", status="PENDING").dec()
            account_balance.observe(float(account.balance))

            logger.info(
                "withdrawal_completed",
                transaction_id=str(transaction.id),
                bank_transaction_id=bank_transaction_id,
                new_balance=str(account.balance),
            )

            self._trigger_webhook_if_configured(transaction, account)

            return transaction

        except Exception as e:
            self.db.rollback()
            logger.error(
                "withdrawal_completion_failed",
                transaction_id=str(transaction.id),
                error=str(e),
            )
            raise

    def fail_withdrawal(
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

        transactions_total.labels(type="withdrawal", status="FAILED").inc()
        active_transactions.labels(type="withdrawal", status="PENDING").dec()
        failed_transactions_total.labels(type="withdrawal", error_code=error_code).inc()

        logger.warning(
            "withdrawal_failed",
            transaction_id=str(transaction_id),
            error_code=error_code,
            error_message=error_message,
        )

        if account:
            self._trigger_webhook_if_configured(transaction, account)

        return transaction
