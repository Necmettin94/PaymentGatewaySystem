from decimal import Decimal
from uuid import UUID

from app.domain.services.base_transaction_service import BaseTransactionService
from app.domain.services.deposit_service import DepositService
from app.domain.services.withdrawal_service import WithdrawalService
from app.infrastructure.external.bank_simulator import BankResponse, BankSimulator
from app.workers.transaction_processor import TransactionStrategy


class DepositStrategy(TransactionStrategy):
    def get_service_class(self):
        return DepositService

    async def call_bank(
        self, bank_simulator: BankSimulator, amount: Decimal, user_id: str, transaction_id: str
    ) -> BankResponse:
        return await bank_simulator.process_deposit(
            amount=amount,
            user_id=user_id,
            transaction_id=transaction_id,
        )

    def complete_transaction(
        self,
        service: BaseTransactionService,
        transaction_id: UUID,
        bank_transaction_id: str,
        bank_response: str,
    ) -> None:
        assert isinstance(service, DepositService)
        service.complete_deposit(
            transaction_id=transaction_id,
            bank_transaction_id=bank_transaction_id,
            bank_response=bank_response,
        )

    def fail_transaction(
        self,
        service: BaseTransactionService,
        transaction_id: UUID,
        error_code: str,
        error_message: str,
        bank_response: str,
    ) -> dict:
        assert isinstance(service, DepositService)
        service.fail_deposit(
            transaction_id=transaction_id,
            error_code=error_code,
            error_message=error_message,
            bank_response=bank_response,
        )
        return {
            "status": "FAILED",
            "transaction_id": str(transaction_id),
            "error": error_message,
        }

    def get_transaction_type_name(self) -> str:
        return "deposit"


class WithdrawalStrategy(TransactionStrategy):
    def get_service_class(self):
        return WithdrawalService

    async def call_bank(
        self, bank_simulator: BankSimulator, amount: Decimal, user_id: str, transaction_id: str
    ) -> BankResponse:
        return await bank_simulator.process_withdrawal(
            amount=amount,
            user_id=user_id,
            transaction_id=transaction_id,
        )

    def complete_transaction(
        self,
        service: BaseTransactionService,
        transaction_id: UUID,
        bank_transaction_id: str,
        bank_response: str,
    ) -> None:
        assert isinstance(service, WithdrawalService)
        service.complete_withdrawal(
            transaction_id=transaction_id,
            bank_transaction_id=bank_transaction_id,
            bank_response=bank_response,
        )

    def fail_transaction(
        self,
        service: BaseTransactionService,
        transaction_id: UUID,
        error_code: str,
        error_message: str,
        bank_response: str,
    ) -> dict:
        assert isinstance(service, WithdrawalService)
        service.fail_withdrawal(
            transaction_id=transaction_id,
            error_code=error_code,
            error_message=error_message,
            bank_response=bank_response,
        )
        return {
            "status": "FAILED",
            "transaction_id": str(transaction_id),
            "error": error_message,
            "refunded": True,
        }

    def get_transaction_type_name(self) -> str:
        return "withdrawal"
