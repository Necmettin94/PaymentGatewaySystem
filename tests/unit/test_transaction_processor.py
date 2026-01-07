from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from app.core.enums import BankResponseStatus, TransactionStatus
from app.infrastructure.external.bank_simulator import BankResponse
from app.workers.strategies import DepositStrategy, WithdrawalStrategy
from app.workers.transaction_processor import GenericTransactionProcessor


@pytest.fixture
def mock_task_instance():
    task = Mock()
    task.request = Mock()
    task.request.retries = 0
    task.max_retries = 3
    task.get_db = Mock()

    db_mock = Mock()
    task.get_db.return_value = db_mock

    return task


@pytest.fixture
def mock_deposit_service():
    service = Mock()
    service.update_status = Mock()
    service.complete_deposit = Mock()
    service.fail_deposit = Mock(return_value={"status": "FAILED"})
    service.mark_pending_review = Mock()
    return service


@pytest.fixture
def mock_withdrawal_service():
    service = Mock()
    service.update_status = Mock()
    service.complete_withdrawal = Mock()
    service.fail_withdrawal = Mock(return_value={"status": "FAILED"})
    service.mark_pending_review = Mock()
    return service


def test_deposit_processor_success(mock_task_instance, mock_deposit_service):
    strategy = DepositStrategy()
    processor = GenericTransactionProcessor(strategy)

    transaction_id = str(uuid4())
    account_id = str(uuid4())
    user_id = str(uuid4())
    amount = "100.00"

    bank_response = BankResponse(
        status=BankResponseStatus.SUCCESS,
        transaction_id="BANK-123",
        message="Deposit successful",
    )

    with patch.object(strategy, "call_bank", new_callable=AsyncMock, return_value=bank_response):
        with patch(
            "app.workers.transaction_processor.GenericTransactionProcessor._handle_success"
        ) as mock_handle_success:
            with patch.object(strategy, "get_service_class") as mock_get_service:
                mock_get_service.return_value = lambda db: mock_deposit_service

                mock_handle_success.return_value = {
                    "status": "SUCCESS",
                    "transaction_id": transaction_id,
                }

                result = processor.process(
                    task_instance=mock_task_instance,
                    transaction_id=transaction_id,
                    account_id=account_id,
                    amount=amount,
                    user_id=user_id,
                )

                assert result["status"] == "SUCCESS"
                mock_deposit_service.update_status.assert_called_once()


def test_withdrawal_processor_success(mock_task_instance, mock_withdrawal_service):
    strategy = WithdrawalStrategy()
    processor = GenericTransactionProcessor(strategy)

    transaction_id = str(uuid4())
    account_id = str(uuid4())
    user_id = str(uuid4())
    amount = "50.00"

    bank_response = BankResponse(
        status=BankResponseStatus.SUCCESS,
        transaction_id="BANK-456",
        message="Withdrawal successful",
    )

    with patch.object(strategy, "call_bank", new_callable=AsyncMock, return_value=bank_response):
        with patch(
            "app.workers.transaction_processor.GenericTransactionProcessor._handle_success"
        ) as mock_handle_success:
            with patch.object(strategy, "get_service_class") as mock_get_service:
                mock_get_service.return_value = lambda db: mock_withdrawal_service

                mock_handle_success.return_value = {
                    "status": "SUCCESS",
                    "transaction_id": transaction_id,
                }

                result = processor.process(
                    task_instance=mock_task_instance,
                    transaction_id=transaction_id,
                    account_id=account_id,
                    amount=amount,
                    user_id=user_id,
                )

                assert result["status"] == "SUCCESS"


def test_processor_handles_bank_timeout(mock_task_instance, mock_deposit_service):
    strategy = DepositStrategy()
    processor = GenericTransactionProcessor(strategy)

    transaction_id = str(uuid4())
    account_id = str(uuid4())
    user_id = str(uuid4())
    amount = "100.00"

    bank_response = BankResponse(
        status=BankResponseStatus.TIMEOUT, error_code="BANK_TIMEOUT", message="Request timeout"
    )

    with patch.object(strategy, "call_bank", new_callable=AsyncMock, return_value=bank_response):
        with patch.object(strategy, "get_service_class") as mock_get_service:
            mock_get_service.return_value = lambda db: mock_deposit_service

            with pytest.raises(Exception) as exc_info:
                processor.process(
                    task_instance=mock_task_instance,
                    transaction_id=transaction_id,
                    account_id=account_id,
                    amount=amount,
                    user_id=user_id,
                )

            assert "TIMEOUT" in str(exc_info.value)


def test_processor_handles_bank_unavailable(mock_task_instance, mock_deposit_service):
    strategy = DepositStrategy()
    processor = GenericTransactionProcessor(strategy)

    transaction_id = str(uuid4())
    account_id = str(uuid4())
    user_id = str(uuid4())
    amount = "100.00"

    bank_response = BankResponse(
        status=BankResponseStatus.UNAVAILABLE,
        error_code="BANK_UNAVAILABLE",
        message="Service unavailable",
    )

    with patch.object(strategy, "call_bank", new_callable=AsyncMock, return_value=bank_response):
        with patch.object(strategy, "get_service_class") as mock_get_service:
            mock_get_service.return_value = lambda db: mock_deposit_service

            with pytest.raises(Exception) as exc_info:
                processor.process(
                    task_instance=mock_task_instance,
                    transaction_id=transaction_id,
                    account_id=account_id,
                    amount=amount,
                    user_id=user_id,
                )

            assert "UNAVAILABLE" in str(exc_info.value)


def test_processor_handles_permanent_failure(mock_task_instance, mock_deposit_service):
    strategy = DepositStrategy()
    processor = GenericTransactionProcessor(strategy)

    transaction_id = str(uuid4())
    account_id = str(uuid4())
    user_id = str(uuid4())
    amount = "100.00"

    bank_response = BankResponse(
        status=BankResponseStatus.INSUFFICIENT_FUNDS,
        error_code="INSUFFICIENT_FUNDS",
        message="Not enough funds",
    )

    with patch.object(strategy, "call_bank", new_callable=AsyncMock, return_value=bank_response):
        with patch.object(strategy, "get_service_class") as mock_get_service:
            with patch.object(strategy, "fail_transaction") as mock_fail:
                mock_get_service.return_value = lambda db: mock_deposit_service
                mock_fail.return_value = {"status": "FAILED"}

                processor.process(
                    task_instance=mock_task_instance,
                    transaction_id=transaction_id,
                    account_id=account_id,
                    amount=amount,
                    user_id=user_id,
                )

                mock_fail.assert_called_once()


def test_processor_max_retries_pending_review(mock_task_instance, mock_deposit_service):
    strategy = DepositStrategy()
    processor = GenericTransactionProcessor(strategy)

    transaction_id = str(uuid4())
    account_id = str(uuid4())
    user_id = str(uuid4())
    amount = "100.00"

    mock_task_instance.request.retries = 3
    mock_task_instance.max_retries = 3

    with patch.object(
        strategy, "call_bank", new_callable=AsyncMock, side_effect=Exception("Database error")
    ):
        with patch.object(strategy, "get_service_class") as mock_get_service:
            mock_get_service.return_value = lambda db: mock_deposit_service

            result = processor.process(
                task_instance=mock_task_instance,
                transaction_id=transaction_id,
                account_id=account_id,
                amount=amount,
                user_id=user_id,
            )

            assert result["status"] == "PENDING_REVIEW"
            mock_deposit_service.mark_pending_review.assert_called_once()


def test_processor_transaction_not_found(mock_task_instance, mock_deposit_service):
    strategy = DepositStrategy()
    processor = GenericTransactionProcessor(strategy)

    transaction_id = str(uuid4())
    account_id = str(uuid4())
    user_id = str(uuid4())
    amount = "100.00"

    with patch.object(
        strategy,
        "call_bank",
        new_callable=AsyncMock,
        side_effect=Exception("Transaction not found"),
    ):
        with patch.object(strategy, "get_service_class") as mock_get_service:
            mock_get_service.return_value = lambda db: mock_deposit_service

            result = processor.process(
                task_instance=mock_task_instance,
                transaction_id=transaction_id,
                account_id=account_id,
                amount=amount,
                user_id=user_id,
            )

            assert result["status"] == "NOT_FOUND"


def test_processor_updates_status_to_processing(mock_task_instance, mock_deposit_service):
    from uuid import UUID

    strategy = DepositStrategy()
    processor = GenericTransactionProcessor(strategy)

    transaction_id = str(uuid4())
    account_id = str(uuid4())
    user_id = str(uuid4())
    amount = "100.00"

    bank_response = BankResponse(
        status=BankResponseStatus.SUCCESS, transaction_id="BANK-123", message="Success"
    )

    with patch.object(strategy, "call_bank", new_callable=AsyncMock, return_value=bank_response):
        with patch.object(strategy, "get_service_class") as mock_get_service:
            with patch.object(strategy, "complete_transaction"):
                mock_get_service.return_value = lambda db: mock_deposit_service

                processor.process(
                    task_instance=mock_task_instance,
                    transaction_id=transaction_id,
                    account_id=account_id,
                    amount=amount,
                    user_id=user_id,
                )

                call_args = mock_deposit_service.update_status.call_args
                assert call_args[0][0] == UUID(transaction_id)
                assert call_args[0][1] == TransactionStatus.PROCESSING


def test_processor_parses_uuid_and_decimal_correctly(mock_task_instance, mock_deposit_service):
    strategy = DepositStrategy()
    processor = GenericTransactionProcessor(strategy)

    transaction_id = str(uuid4())
    account_id = str(uuid4())
    user_id = str(uuid4())
    amount = "123.45"

    bank_response = BankResponse(
        status=BankResponseStatus.SUCCESS, transaction_id="BANK-123", message="Success"
    )

    with patch.object(strategy, "call_bank", new_callable=AsyncMock, return_value=bank_response):
        with patch.object(strategy, "get_service_class") as mock_get_service:
            with patch.object(strategy, "complete_transaction"):
                mock_get_service.return_value = lambda db: mock_deposit_service

                result = processor.process(
                    task_instance=mock_task_instance,
                    transaction_id=transaction_id,
                    account_id=account_id,
                    amount=amount,
                    user_id=user_id,
                )

                assert result is not None
