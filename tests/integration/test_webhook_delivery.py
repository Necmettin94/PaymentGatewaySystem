import json
from decimal import Decimal
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.enums import TransactionStatus, TransactionType
from app.domain.services.deposit_service import DepositService
from app.infrastructure.models import Account, Transaction, User, WebhookDeliveryStatus
from app.infrastructure.repositories.webhook_repository import WebhookRepository
from app.main import app


class TestWebhookDeliveryIntegration:

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    def test_webhook_triggered_on_successful_deposit(self, db: Session):

        user = User(
            email=f"webhook_test_{uuid4()}@example.com",
            full_name="Webhook Test User",
            hashed_password="hashed",
            is_active=True,
            webhook_url="https://example.com/webhook",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        account = Account(
            user_id=user.id,
            balance=Decimal("0.00"),
            currency="USD",
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        transaction = Transaction(
            account_id=account.id,
            transaction_type=TransactionType.DEPOSIT,
            amount=Decimal("100.00"),
            currency="USD",
            status=TransactionStatus.PROCESSING,
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)

        with patch("httpx.Client") as mock_client_class:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_client = mock_client_class.return_value.__enter__.return_value
            mock_client.post.return_value = mock_response

            deposit_service = DepositService(db)
            deposit_service.complete_deposit(
                transaction_id=transaction.id,
                bank_transaction_id="BANK_TX_123",
                bank_response="Success",
            )

            webhook_repo = WebhookRepository(db)
            deliveries = webhook_repo.get_by_transaction_id(transaction.id)

            assert len(deliveries) == 1
            delivery = deliveries[0]
            assert delivery.status == WebhookDeliveryStatus.PENDING
            assert delivery.webhook_url == user.webhook_url

            payload = json.loads(delivery.payload)
            assert payload["event"] == "transaction.completed"
            assert payload["transaction"]["id"] == str(transaction.id)
            assert payload["transaction"]["type"] == TransactionType.DEPOSIT
            assert payload["transaction"]["status"] == TransactionStatus.SUCCESS
            assert Decimal(payload["transaction"]["amount"]) == Decimal("100.00")

    def test_webhook_triggered_on_failed_deposit(self, db: Session):

        user = User(
            email=f"webhook_fail_test_{uuid4()}@example.com",
            full_name="Webhook Fail Test User",
            hashed_password="hashed",
            is_active=True,
            webhook_url="https://example.com/webhook",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        account = Account(
            user_id=user.id,
            balance=Decimal("0.00"),
            currency="USD",
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        transaction = Transaction(
            account_id=account.id,
            transaction_type=TransactionType.DEPOSIT,
            amount=Decimal("100.00"),
            currency="USD",
            status=TransactionStatus.PROCESSING,
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)

        with patch("httpx.Client") as mock_client_class:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_client = mock_client_class.return_value.__enter__.return_value
            mock_client.post.return_value = mock_response

            deposit_service = DepositService(db)
            deposit_service.fail_deposit(
                transaction_id=transaction.id,
                error_code="BANK_ERROR",
                error_message="Bank processing failed",
            )

            webhook_repo = WebhookRepository(db)
            deliveries = webhook_repo.get_by_transaction_id(transaction.id)

            assert len(deliveries) == 1
            delivery = deliveries[0]

            payload = json.loads(delivery.payload)
            assert payload["event"] == "transaction.failed"
            assert payload["transaction"]["status"] == TransactionStatus.FAILED
            assert payload["transaction"]["error_code"] == "BANK_ERROR"

    def test_webhook_not_triggered_when_webhook_url_is_null(self, db: Session):

        user = User(
            email=f"no_webhook_{uuid4()}@example.com",
            full_name="No Webhook User",
            hashed_password="hashed",
            is_active=True,
            webhook_url=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        account = Account(
            user_id=user.id,
            balance=Decimal("0.00"),
            currency="USD",
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        transaction = Transaction(
            account_id=account.id,
            transaction_type=TransactionType.DEPOSIT,
            amount=Decimal("100.00"),
            currency="USD",
            status=TransactionStatus.PROCESSING,
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)

        deposit_service = DepositService(db)
        deposit_service.complete_deposit(
            transaction_id=transaction.id,
            bank_transaction_id="BANK_TX_123",
            bank_response="Success",
        )

        webhook_repo = WebhookRepository(db)
        deliveries = webhook_repo.get_by_transaction_id(transaction.id)

        assert len(deliveries) == 0

    def test_webhook_delivery_repository_operations(self, db: Session):

        user = User(
            email=f"test_{uuid4()}@example.com",
            full_name="Test User",
            hashed_password="hashed",
        )
        db.add(user)
        db.flush()

        account = Account(user_id=user.id, balance=Decimal("0"), currency="USD")
        db.add(account)
        db.flush()

        transaction = Transaction(
            account_id=account.id,
            transaction_type=TransactionType.DEPOSIT,
            amount=Decimal("100"),
            currency="USD",
            status=TransactionStatus.SUCCESS,
        )
        db.add(transaction)
        db.commit()

        webhook_repo = WebhookRepository(db)
        delivery = webhook_repo.create_delivery(
            transaction_id=transaction.id,
            webhook_url="https://example.com/webhook",
            payload={
                "event": "transaction.completed",
                "transaction": {"id": str(transaction.id), "status": "SUCCESS"},
            },
        )
        db.commit()
        db.refresh(delivery)

        assert delivery.status == WebhookDeliveryStatus.PENDING
        assert delivery.attempt_count == 0
        assert delivery.max_attempts == 5

        webhook_repo.mark_as_success(
            delivery_id=delivery.id, http_status_code=200, response_body="OK"
        )
        db.refresh(delivery)

        assert delivery.status == WebhookDeliveryStatus.SUCCESS
        assert delivery.http_status_code == 200
        assert delivery.response_body == "OK"

    def test_webhook_delivery_mark_as_failed(self, db: Session):

        user = User(email=f"test_{uuid4()}@example.com", full_name="Test", hashed_password="h")
        db.add(user)
        db.flush()

        account = Account(user_id=user.id, balance=Decimal("0"), currency="USD")
        db.add(account)
        db.flush()

        transaction = Transaction(
            account_id=account.id,
            transaction_type=TransactionType.DEPOSIT,
            amount=Decimal("100"),
            currency="USD",
            status=TransactionStatus.SUCCESS,
        )
        db.add(transaction)
        db.commit()

        webhook_repo = WebhookRepository(db)
        delivery = webhook_repo.create_delivery(
            transaction_id=transaction.id,
            webhook_url="https://example.com/webhook",
            payload={"event": "test"},
        )
        db.commit()
        db.refresh(delivery)

        webhook_repo.mark_as_failed(
            delivery_id=delivery.id, error_message="404 Not Found", http_status_code=404
        )
        db.refresh(delivery)

        assert delivery.status == WebhookDeliveryStatus.FAILED
        assert delivery.http_status_code == 404
        assert "404" in delivery.error_message

    def test_webhook_delivery_exponential_backoff_configuration(self, db: Session):
        from app.workers.tasks.webhook_tasks import WebhookDeliveryTask

        assert WebhookDeliveryTask.retry_backoff is True
        assert WebhookDeliveryTask.retry_backoff_max == 600
        assert WebhookDeliveryTask.retry_jitter is True
        assert WebhookDeliveryTask.retry_kwargs["max_retries"] == 5

    def test_multiple_webhook_deliveries_tracked_separately(self, db: Session):

        user = User(email=f"test_{uuid4()}@example.com", full_name="Test", hashed_password="h")
        db.add(user)
        db.flush()

        account = Account(user_id=user.id, balance=Decimal("0"), currency="USD")
        db.add(account)
        db.flush()

        transaction = Transaction(
            account_id=account.id,
            transaction_type=TransactionType.DEPOSIT,
            amount=Decimal("100"),
            currency="USD",
            status=TransactionStatus.SUCCESS,
        )
        db.add(transaction)
        db.commit()

        webhook_repo = WebhookRepository(db)

        delivery1 = webhook_repo.create_delivery(
            transaction_id=transaction.id,
            webhook_url="https://example.com/webhook",
            payload={"attempt": 1},
        )

        delivery2 = webhook_repo.create_delivery(
            transaction_id=transaction.id,
            webhook_url="https://example.com/webhook",
            payload={"attempt": 2},
        )

        db.commit()

        deliveries = webhook_repo.get_by_transaction_id(transaction.id)
        assert len(deliveries) == 2
        assert delivery1.id != delivery2.id

    def test_webhook_repository_response_truncation(self, db: Session):

        user = User(email=f"test_{uuid4()}@example.com", full_name="Test", hashed_password="h")
        db.add(user)
        db.flush()

        account = Account(user_id=user.id, balance=Decimal("0"), currency="USD")
        db.add(account)
        db.flush()

        transaction = Transaction(
            account_id=account.id,
            transaction_type=TransactionType.DEPOSIT,
            amount=Decimal("100"),
            currency="USD",
            status=TransactionStatus.SUCCESS,
        )
        db.add(transaction)
        db.commit()

        webhook_repo = WebhookRepository(db)
        delivery = webhook_repo.create_delivery(
            transaction_id=transaction.id,
            webhook_url="https://example.com/webhook",
            payload={"event": "test"},
        )
        db.commit()
        db.refresh(delivery)

        long_response = "x" * 5000
        webhook_repo.mark_as_success(
            delivery_id=delivery.id, http_status_code=200, response_body=long_response
        )
        db.refresh(delivery)

        assert len(delivery.response_body) == 1000
        assert delivery.response_body == "x" * 1000

    def test_webhook_includes_account_balance_in_payload(self, db: Session):

        user = User(
            email=f"balance_test_{uuid4()}@example.com",
            full_name="Balance Test",
            hashed_password="hashed",
            webhook_url="https://example.com/webhook",
        )
        db.add(user)
        db.commit()

        account = Account(
            user_id=user.id,
            balance=Decimal("500.00"),
            currency="USD",
        )
        db.add(account)
        db.commit()

        transaction = Transaction(
            account_id=account.id,
            transaction_type=TransactionType.DEPOSIT,
            amount=Decimal("100.00"),
            currency="USD",
            status=TransactionStatus.PROCESSING,
        )
        db.add(transaction)
        db.commit()

        with patch("httpx.Client") as mock_client_class:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_client = mock_client_class.return_value.__enter__.return_value
            mock_client.post.return_value = mock_response

            deposit_service = DepositService(db)
            deposit_service.complete_deposit(
                transaction_id=transaction.id,
                bank_transaction_id="BANK_TX",
                bank_response="Success",
            )

            webhook_repo = WebhookRepository(db)
            deliveries = webhook_repo.get_by_transaction_id(transaction.id)
            payload = json.loads(deliveries[0].payload)

            assert Decimal(payload["account"]["balance"]) == Decimal("600.00")
