import asyncio
import random
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from app.config import settings
from app.core.enums import BankResponseStatus
from app.core.logging import get_logger
from app.infrastructure.external.circuit_breaker import CircuitBreaker

logger = get_logger(__name__)

# Using 5 as threshold - tried 3 but it was too sensitive for random failures
_bank_circuit_breaker = CircuitBreaker(
    name="bank_api",
    failure_threshold=5,
    timeout_seconds=30,
    success_threshold=2,
)


@dataclass
class BankResponse:
    status: BankResponseStatus
    transaction_id: str | None = None
    message: str | None = None
    error_code: str | None = None


class BankSimulator:
    def __init__(
        self,
        min_delay: int | None = None,
        max_delay: int | None = None,
        success_rate: float | None = None,
    ):
        self.min_delay = min_delay or settings.bank_simulator_min_delay
        self.max_delay = max_delay or settings.bank_simulator_max_delay
        self.success_rate = success_rate or settings.bank_simulator_success_rate

    async def _simulate_network_delay(self) -> None:
        delay = random.uniform(self.min_delay, self.max_delay)  # nosec
        logger.info("bank_processing_delay", delay_seconds=delay)
        await asyncio.sleep(delay)

    def _should_succeed(self) -> bool:
        return random.random() < self.success_rate  # nosec

    async def process_deposit(
        self,
        amount: Decimal,
        user_id: str,
        transaction_id: str,
    ) -> BankResponse:
        if not _bank_circuit_breaker.can_execute():
            logger.warning(
                "bank_deposit_circuit_open",
                transaction_id=transaction_id,
                circuit_state=_bank_circuit_breaker.state,
            )
            return BankResponse(
                status=BankResponseStatus.UNAVAILABLE,
                message="Bank service is currently unavailable (circuit breaker OPEN)",
                error_code="CIRCUIT_BREAKER_OPEN",
            )

        logger.info(
            "bank_deposit_initiated",
            amount=str(amount),
            user_id=user_id,
            transaction_id=transaction_id,
        )

        try:
            await self._simulate_network_delay()

            if self._should_succeed():
                bank_tx_id = f"BANK-DEP-{uuid4().hex[:12].upper()}"
                logger.info(
                    "bank_deposit_success",
                    bank_transaction_id=bank_tx_id,
                    amount=str(amount),
                )
                _bank_circuit_breaker.record_success()
                return BankResponse(
                    status=BankResponseStatus.SUCCESS,
                    transaction_id=bank_tx_id,
                    message="Deposit processed successfully",
                )
            else:
                error_response = self._generate_error_scenario()
                logger.warning(
                    "bank_deposit_failed",
                    error_code=error_response.error_code,
                    message=error_response.message,
                )

                if error_response.status in [
                    BankResponseStatus.UNAVAILABLE,
                    BankResponseStatus.TIMEOUT,
                ]:
                    _bank_circuit_breaker.record_failure()

                return error_response

        except Exception as e:
            _bank_circuit_breaker.record_failure()
            logger.error(
                "bank_deposit_exception",
                transaction_id=transaction_id,
                error=str(e),
            )
            raise

    async def process_withdrawal(
        self,
        amount: Decimal,
        user_id: str,
        transaction_id: str,
    ) -> BankResponse:
        if not _bank_circuit_breaker.can_execute():
            logger.warning(
                "bank_withdrawal_circuit_open",
                transaction_id=transaction_id,
                circuit_state=_bank_circuit_breaker.state,
            )
            return BankResponse(
                status=BankResponseStatus.UNAVAILABLE,
                message="Bank service is currently unavailable (circuit breaker OPEN)",
                error_code="CIRCUIT_BREAKER_OPEN",
            )

        logger.info(
            "bank_withdrawal_initiated",
            amount=str(amount),
            user_id=user_id,
            transaction_id=transaction_id,
        )

        try:
            await self._simulate_network_delay()

            if self._should_succeed():
                bank_tx_id = f"BANK-WTH-{uuid4().hex[:12].upper()}"
                logger.info(
                    "bank_withdrawal_success",
                    bank_transaction_id=bank_tx_id,
                    amount=str(amount),
                )
                _bank_circuit_breaker.record_success()
                return BankResponse(
                    status=BankResponseStatus.SUCCESS,
                    transaction_id=bank_tx_id,
                    message="Withdrawal processed successfully",
                )
            else:
                error_response = self._generate_error_scenario()
                logger.warning(
                    "bank_withdrawal_failed",
                    error_code=error_response.error_code,
                    message=error_response.message,
                )
                if error_response.status in [
                    BankResponseStatus.UNAVAILABLE,
                    BankResponseStatus.TIMEOUT,
                ]:
                    _bank_circuit_breaker.record_failure()

                return error_response

        except Exception as e:
            _bank_circuit_breaker.record_failure()
            logger.error(
                "bank_withdrawal_exception",
                transaction_id=transaction_id,
                error=str(e),
            )
            raise

    @staticmethod
    def _generate_error_scenario() -> BankResponse:
        error_type = random.choices(  # nosec
            ["unavailable", "timeout", "insufficient_funds"],
            weights=[0.4, 0.3, 0.3],
        )[0]

        if error_type == "unavailable":
            return BankResponse(
                status=BankResponseStatus.UNAVAILABLE,
                message="Bank service temporarily unavailable",
                error_code="BANK_UNAVAILABLE",
            )
        elif error_type == "timeout":
            return BankResponse(
                status=BankResponseStatus.TIMEOUT,
                message="Bank processing timeout",
                error_code="BANK_TIMEOUT",
            )
        else:
            return BankResponse(
                status=BankResponseStatus.INSUFFICIENT_FUNDS,
                message="Insufficient funds in external account",
                error_code="INSUFFICIENT_FUNDS",
            )


_bank_simulator: BankSimulator | None = None


def get_bank_simulator() -> BankSimulator:
    global _bank_simulator
    if _bank_simulator is None:
        _bank_simulator = BankSimulator()
    return _bank_simulator


def get_circuit_breaker_state() -> dict:
    return _bank_circuit_breaker.get_state()
