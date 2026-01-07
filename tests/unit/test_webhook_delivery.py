import json
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.infrastructure.models import WebhookDelivery, WebhookDeliveryStatus
from app.infrastructure.repositories.webhook_repository import WebhookRepository
from app.workers.tasks.webhook_tasks import send_webhook_notification


class TestWebhookDeliveryTask:

    @pytest.fixture
    def mock_db(self) -> Mock:
        return MagicMock(spec=Session)

    @pytest.fixture
    def sample_delivery(self) -> WebhookDelivery:
        return WebhookDelivery(
            id=uuid4(),
            transaction_id=uuid4(),
            webhook_url="https://example.com/webhook",
            payload=json.dumps(
                {
                    "event": "transaction.completed",
                    "transaction": {
                        "id": str(uuid4()),
                        "type": "DEPOSIT",
                        "amount": "100.00",
                        "status": "SUCCESS",
                    },
                }
            ),
            status=WebhookDeliveryStatus.PENDING,
            attempt_count=0,
            max_attempts=5,
        )

    def test_successful_webhook_delivery(self, mock_db: Mock, sample_delivery: WebhookDelivery):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        with patch("app.workers.tasks.webhook_tasks.SessionLocal", return_value=mock_db):
            with patch("httpx.Client") as mock_client_class:
                mock_db.query().filter().first.return_value = sample_delivery
                mock_client = mock_client_class.return_value.__enter__.return_value
                mock_client.post.return_value = mock_response
                result = send_webhook_notification(str(sample_delivery.id))

                assert result["success"] is True
                assert result["http_status_code"] == 200
                assert sample_delivery.status == WebhookDeliveryStatus.SUCCESS
                assert sample_delivery.attempt_count == 1
                mock_db.commit.assert_called()

    def test_webhook_delivery_with_4xx_error_no_retry(
        self, mock_db: Mock, sample_delivery: WebhookDelivery
    ):
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        with patch("app.workers.tasks.webhook_tasks.SessionLocal", return_value=mock_db):
            with patch("httpx.Client") as mock_client_class:
                mock_db.query().filter().first.return_value = sample_delivery
                mock_client = mock_client_class.return_value.__enter__.return_value
                mock_client.post.return_value = mock_response

                result = send_webhook_notification(str(sample_delivery.id))

                assert result["success"] is False
                assert sample_delivery.status == WebhookDeliveryStatus.FAILED
                assert "404" in sample_delivery.error_message

    def test_webhook_delivery_not_found_returns_error(self, mock_db: Mock):
        with patch("app.workers.tasks.webhook_tasks.SessionLocal", return_value=mock_db):
            mock_db.query().filter().first.return_value = None
            result = send_webhook_notification(str(uuid4()))

            assert result["success"] is False
            assert "not found" in result["error"].lower()

    def test_webhook_payload_includes_correct_headers(
        self, mock_db: Mock, sample_delivery: WebhookDelivery
    ):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        with patch("app.workers.tasks.webhook_tasks.SessionLocal", return_value=mock_db):
            with patch("httpx.Client") as mock_client_class:
                mock_db.query().filter().first.return_value = sample_delivery
                mock_client = mock_client_class.return_value.__enter__.return_value
                mock_client.post.return_value = mock_response
                send_webhook_notification(str(sample_delivery.id))

                call_args = mock_client.post.call_args
                headers = call_args.kwargs["headers"]

                assert headers["Content-Type"] == "application/json"
                assert headers["User-Agent"] == "PaymentGateway-Webhook/1.0"
                assert headers["X-Webhook-Delivery-ID"] == str(sample_delivery.id)

    def test_webhook_response_body_truncated_to_1000_chars(
        self, mock_db: Mock, sample_delivery: WebhookDelivery
    ):
        long_response = "x" * 2000
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = long_response

        with patch("app.workers.tasks.webhook_tasks.SessionLocal", return_value=mock_db):
            with patch("httpx.Client") as mock_client_class:
                mock_db.query().filter().first.return_value = sample_delivery
                mock_client = mock_client_class.return_value.__enter__.return_value
                mock_client.post.return_value = mock_response

                send_webhook_notification(str(sample_delivery.id))

                assert len(sample_delivery.response_body) == 1000


class TestWebhookRepository:
    @pytest.fixture
    def mock_db(self) -> Mock:
        return MagicMock(spec=Session)

    @pytest.fixture
    def webhook_repo(self, mock_db: Mock) -> WebhookRepository:
        return WebhookRepository(mock_db)

    def test_create_delivery(self, webhook_repo: WebhookRepository, mock_db: Mock):
        transaction_id = uuid4()
        webhook_url = "https://example.com/webhook"
        payload = {"event": "test"}

        delivery = webhook_repo.create_delivery(
            transaction_id=transaction_id,
            webhook_url=webhook_url,
            payload=payload,
        )

        assert delivery.transaction_id == transaction_id
        assert delivery.webhook_url == webhook_url
        assert delivery.payload == json.dumps(payload)
        assert delivery.status == WebhookDeliveryStatus.PENDING
        assert delivery.attempt_count == 0
        assert delivery.max_attempts == 5

        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    def test_get_pending_deliveries(self, webhook_repo: WebhookRepository, mock_db: Mock):
        mock_db.query().filter().filter().order_by().limit().all.return_value = []
        deliveries = webhook_repo.get_pending_deliveries(limit=100)

        assert isinstance(deliveries, list)
        mock_db.query.assert_called()

    def test_mark_as_success(self, webhook_repo: WebhookRepository, mock_db: Mock):
        delivery = WebhookDelivery(
            id=uuid4(),
            transaction_id=uuid4(),
            webhook_url="https://example.com/webhook",
            payload="{}",
            status=WebhookDeliveryStatus.SENDING,
        )

        mock_db.query().filter().first.return_value = delivery

        result = webhook_repo.mark_as_success(
            delivery_id=delivery.id,
            http_status_code=200,
            response_body="OK",
        )

        assert result.status == WebhookDeliveryStatus.SUCCESS
        assert result.http_status_code == 200
        assert result.response_body == "OK"
        mock_db.commit.assert_called_once()

    def test_mark_as_failed(self, webhook_repo: WebhookRepository, mock_db: Mock):
        delivery = WebhookDelivery(
            id=uuid4(),
            transaction_id=uuid4(),
            webhook_url="https://example.com/webhook",
            payload="{}",
            status=WebhookDeliveryStatus.SENDING,
        )

        mock_db.query().filter().first.return_value = delivery

        result = webhook_repo.mark_as_failed(
            delivery_id=delivery.id,
            error_message="Connection timeout",
            http_status_code=None,
        )

        assert result.status == WebhookDeliveryStatus.FAILED
        assert "Connection timeout" in result.error_message
        mock_db.commit.assert_called_once()
