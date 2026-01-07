from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.domain.services.deposit_service import DepositService
from app.domain.services.withdrawal_service import WithdrawalService
from app.infrastructure.external.bank_simulator import BankResponse, BankResponseStatus
from app.workers.strategies import DepositStrategy, WithdrawalStrategy


@pytest.fixture
def mock_deposit_service():
    service = Mock(spec=DepositService)
    service.complete_deposit = Mock()
    service.fail_deposit = Mock(return_value={"status": "FAILED"})
    return service


@pytest.fixture
def mock_withdrawal_service():
    service = Mock(spec=WithdrawalService)
    service.complete_withdrawal = Mock()
    service.fail_withdrawal = Mock(return_value={"status": "FAILED"})
    return service


@pytest.fixture
def mock_bank_simulator():
    simulator = Mock()
    return simulator


def test_deposit_strategy_returns_correct_service_class():
    strategy = DepositStrategy()
    service_class = strategy.get_service_class()

    assert service_class == DepositService


def test_withdrawal_strategy_returns_correct_service_class():
    strategy = WithdrawalStrategy()
    service_class = strategy.get_service_class()

    assert service_class == WithdrawalService


@pytest.mark.asyncio
async def test_deposit_strategy_calls_bank_deposit(mock_bank_simulator):
    from unittest.mock import AsyncMock

    strategy = DepositStrategy()

    transaction_id = str(uuid4())
    user_id = str(uuid4())
    amount = Decimal("100.00")

    expected_response = BankResponse(
        status=BankResponseStatus.SUCCESS, transaction_id="BANK-123", message="Success"
    )
    mock_bank_simulator.process_deposit = AsyncMock(return_value=expected_response)

    result = await strategy.call_bank(
        bank_simulator=mock_bank_simulator,
        amount=amount,
        user_id=user_id,
        transaction_id=transaction_id,
    )

    mock_bank_simulator.process_deposit.assert_called_once_with(
        amount=amount, user_id=user_id, transaction_id=transaction_id
    )
    assert result == expected_response


@pytest.mark.asyncio
async def test_withdrawal_strategy_calls_bank_withdrawal(mock_bank_simulator):
    from unittest.mock import AsyncMock

    strategy = WithdrawalStrategy()

    transaction_id = str(uuid4())
    user_id = str(uuid4())
    amount = Decimal("50.00")

    expected_response = BankResponse(
        status=BankResponseStatus.SUCCESS, transaction_id="BANK-456", message="Success"
    )
    mock_bank_simulator.process_withdrawal = AsyncMock(return_value=expected_response)

    result = await strategy.call_bank(
        bank_simulator=mock_bank_simulator,
        amount=amount,
        user_id=user_id,
        transaction_id=transaction_id,
    )

    mock_bank_simulator.process_withdrawal.assert_called_once_with(
        amount=amount, user_id=user_id, transaction_id=transaction_id
    )
    assert result == expected_response


def test_deposit_strategy_complete_transaction(mock_deposit_service):
    strategy = DepositStrategy()

    transaction_id = uuid4()
    bank_transaction_id = "BANK-123"
    bank_response = "Success"

    strategy.complete_transaction(
        service=mock_deposit_service,
        transaction_id=transaction_id,
        bank_transaction_id=bank_transaction_id,
        bank_response=bank_response,
    )

    mock_deposit_service.complete_deposit.assert_called_once_with(
        transaction_id=transaction_id,
        bank_transaction_id=bank_transaction_id,
        bank_response=bank_response,
    )


def test_withdrawal_strategy_complete_transaction(mock_withdrawal_service):
    strategy = WithdrawalStrategy()

    transaction_id = uuid4()
    bank_transaction_id = "BANK-456"
    bank_response = "Success"

    strategy.complete_transaction(
        service=mock_withdrawal_service,
        transaction_id=transaction_id,
        bank_transaction_id=bank_transaction_id,
        bank_response=bank_response,
    )

    mock_withdrawal_service.complete_withdrawal.assert_called_once_with(
        transaction_id=transaction_id,
        bank_transaction_id=bank_transaction_id,
        bank_response=bank_response,
    )


def test_deposit_strategy_fail_transaction(mock_deposit_service):
    strategy = DepositStrategy()

    transaction_id = uuid4()
    error_code = "BANK_ERROR"
    error_message = "Bank processing failed"
    bank_response = "Error details"

    result = strategy.fail_transaction(
        service=mock_deposit_service,
        transaction_id=transaction_id,
        error_code=error_code,
        error_message=error_message,
        bank_response=bank_response,
    )

    mock_deposit_service.fail_deposit.assert_called_once_with(
        transaction_id=transaction_id,
        error_code=error_code,
        error_message=error_message,
        bank_response=bank_response,
    )

    assert result["status"] == "FAILED"
    assert result["error"] == error_message


def test_withdrawal_strategy_fail_transaction(mock_withdrawal_service):
    strategy = WithdrawalStrategy()

    transaction_id = uuid4()
    error_code = "INSUFFICIENT_FUNDS"
    error_message = "Not enough balance"
    bank_response = "Error details"

    result = strategy.fail_transaction(
        service=mock_withdrawal_service,
        transaction_id=transaction_id,
        error_code=error_code,
        error_message=error_message,
        bank_response=bank_response,
    )

    mock_withdrawal_service.fail_withdrawal.assert_called_once_with(
        transaction_id=transaction_id,
        error_code=error_code,
        error_message=error_message,
        bank_response=bank_response,
    )

    assert result["status"] == "FAILED"
    assert result["refunded"] is True


def test_deposit_strategy_get_transaction_type_name():
    strategy = DepositStrategy()
    assert strategy.get_transaction_type_name() == "deposit"


def test_withdrawal_strategy_get_transaction_type_name():
    strategy = WithdrawalStrategy()
    assert strategy.get_transaction_type_name() == "withdrawal"
