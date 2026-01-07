import asyncio
from abc import ABC, abstractmethod
from decimal import Decimal
from uuid import UUID

from celery.utils.log import get_task_logger

from app.core.enums import BankResponseStatus, TransactionStatus
from app.domain.services.base_transaction_service import BaseTransactionService
from app.infrastructure.external.bank_simulator import BankResponse, get_bank_simulator

logger = get_task_logger(__name__)


class TransactionStrategy(ABC):
    @abstractmethod
    def get_service_class(self):
        pass

    @abstractmethod
    async def call_bank(
        self, bank_simulator, amount: Decimal, user_id: str, transaction_id: str
    ) -> BankResponse:
        pass

    @abstractmethod
    def complete_transaction(
        self,
        service: BaseTransactionService,
        transaction_id: UUID,
        bank_transaction_id: str,
        bank_response: str,
    ) -> None:
        pass

    @abstractmethod
    def fail_transaction(
        self,
        service: BaseTransactionService,
        transaction_id: UUID,
        error_code: str,
        error_message: str,
        bank_response: str,
    ) -> dict:
        pass

    @abstractmethod
    def get_transaction_type_name(self) -> str:
        pass


class GenericTransactionProcessor:
    def __init__(self, strategy: TransactionStrategy):
        self.strategy = strategy

    def process(
        self,
        task_instance,
        transaction_id: str,
        account_id: str,
        amount: str,
        user_id: str,
    ) -> dict:
        type_name = self.strategy.get_transaction_type_name()
        logger.info(f"Processing {type_name}: transaction_id={transaction_id}, amount={amount}")
        tx_id = UUID(transaction_id)
        decimal_amount = Decimal(amount)
        db = task_instance.get_db()

        try:
            service_class = self.strategy.get_service_class()
            service = service_class(db)
            service.update_status(tx_id, TransactionStatus.PROCESSING)
            logger.info(f"{type_name.capitalize()} {transaction_id} status updated to PROCESSING")

            bank_simulator = get_bank_simulator()
            bank_response = asyncio.run(
                self.strategy.call_bank(
                    bank_simulator=bank_simulator,
                    amount=decimal_amount,
                    user_id=user_id,
                    transaction_id=transaction_id,
                )
            )
            logger.info(f"Bank response for {type_name} {transaction_id}: {bank_response.status}")
            if bank_response.status == BankResponseStatus.SUCCESS:
                return self._handle_success(
                    service, tx_id, transaction_id, bank_response, type_name
                )
            elif bank_response.status in [
                BankResponseStatus.TIMEOUT,
                BankResponseStatus.UNAVAILABLE,
            ]:
                return self._handle_transient_error(transaction_id, bank_response, type_name)
            else:
                return self._handle_permanent_failure(
                    service, tx_id, transaction_id, bank_response, type_name
                )
        except Exception as e:
            return self._handle_exception(task_instance, tx_id, transaction_id, e, type_name)
        finally:
            db.close()

    def _handle_success(
        self,
        service: BaseTransactionService,
        tx_id: UUID,
        transaction_id: str,
        bank_response: BankResponse,
        type_name: str,
    ) -> dict:
        self.strategy.complete_transaction(
            service=service,
            transaction_id=tx_id,
            bank_transaction_id=bank_response.transaction_id or "",
            bank_response=bank_response.message or "",
        )

        logger.info(f"{type_name.capitalize()} {transaction_id} completed successfully")

        return {
            "status": "SUCCESS",
            "transaction_id": transaction_id,
            "bank_transaction_id": bank_response.transaction_id,
        }

    def _handle_transient_error(
        self, transaction_id: str, bank_response: BankResponse, type_name: str
    ) -> dict:
        logger.warning(
            f"{type_name.capitalize()} {transaction_id} failed with transient error: "
            f"{bank_response.error_code}"
        )
        raise Exception(f"Bank {bank_response.status}: {bank_response.message}")

    def _handle_permanent_failure(
        self,
        service: BaseTransactionService,
        tx_id: UUID,
        transaction_id: str,
        bank_response: BankResponse,
        type_name: str,
    ) -> dict:
        result = self.strategy.fail_transaction(
            service=service,
            transaction_id=tx_id,
            error_code=bank_response.error_code or "BANK_ERROR",
            error_message=bank_response.message or "Bank processing failed",
            bank_response=str(bank_response),
        )

        logger.error(f"{type_name.capitalize()} {transaction_id} failed permanently")
        return result

    def _handle_exception(
        self,
        task_instance,
        tx_id: UUID,
        transaction_id: str,
        error: Exception,
        type_name: str,
    ) -> dict:
        if "not found" in str(error).lower():
            logger.warning(
                f"{type_name.capitalize()} {transaction_id} transaction not found - "
                f"likely rolled back in tests or deleted"
            )
            return {
                "status": "NOT_FOUND",
                "transaction_id": transaction_id,
                "error": "Transaction not found",
            }

        if task_instance.request.retries >= task_instance.max_retries:
            return self._mark_for_review(task_instance, tx_id, transaction_id, error, type_name)
        else:
            logger.warning(
                f"{type_name.capitalize()} {transaction_id} retry "
                f"{task_instance.request.retries}/{task_instance.max_retries}"
            )
            raise

    def _mark_for_review(
        self,
        task_instance,
        tx_id: UUID,
        transaction_id: str,
        error: Exception,
        type_name: str,
    ) -> dict[str, str]:
        try:
            review_db = task_instance.get_db()
            try:
                service_class = self.strategy.get_service_class()
                review_service = service_class(review_db)

                reason_suffix = ""
                if type_name == "withdrawal":
                    reason_suffix = " Balance reserved, requires manual review."

                review_service.mark_pending_review(
                    transaction_id=tx_id,
                    reason=f"Max retries exceeded: {str(error)}.{reason_suffix}",
                )

                logger.error(
                    f"{type_name.capitalize()} {transaction_id} marked for review after "
                    f"{task_instance.request.retries} retries"
                )
            finally:
                review_db.close()
        except Exception as review_error:
            logger.error(f"Failed to mark {type_name} {transaction_id} for review: {review_error}")

        result = {
            "status": "PENDING_REVIEW",
            "transaction_id": transaction_id,
            "error": str(error),
        }

        if type_name == "withdrawal":
            result["note"] = "Balance reserved, manual review required"

        return result
