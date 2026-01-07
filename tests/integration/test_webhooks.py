from decimal import Decimal

from app.infrastructure.models import WebhookDeliveryStatus
from app.infrastructure.repositories.webhook_repository import WebhookRepository


class TestWebhookDeliveryEndpoints:

    def test_get_webhook_deliveries_empty(self, client, auth_headers):
        response = client.get("/webhooks/deliveries", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "deliveries" in data
        assert "total" in data
        assert data["total"] == 0
        assert len(data["deliveries"]) == 0

    def test_get_webhook_deliveries_with_data(
        self, client, auth_headers, test_user, test_account, db
    ):
        from app.domain.services.deposit_service import DepositService

        test_user.webhook_url = "https://webhook.site/test"
        db.commit()

        deposit_service = DepositService(db)
        transaction = deposit_service.create_pending_deposit(
            account_id=test_account.id,
            amount=Decimal("100.00"),
            currency="USD",
        )
        deposit_service.complete_deposit(
            transaction_id=transaction.id,
            bank_transaction_id="TEST-BANK-ID",
            bank_response="Test success",
        )

        response = client.get("/webhooks/deliveries", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["deliveries"]) == 1

        delivery = data["deliveries"][0]
        assert "id" in delivery
        assert "transaction_id" in delivery
        assert delivery["transaction_id"] == str(transaction.id)
        assert "webhook_url" in delivery
        assert delivery["webhook_url"] == "https://webhook.site/test"
        assert "status" in delivery
        assert delivery["status"] == "PENDING"
        assert "attempt_count" in delivery
        assert delivery["attempt_count"] == 0

    def test_get_webhook_delivery_unauthorized(self, client, auth_headers, db):

        fake_id = "00000000-0000-0000-0000-000000000000"

        response = client.get(
            f"/webhooks/deliveries/{fake_id}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_filter_webhook_deliveries_by_transaction(
        self, client, auth_headers, test_user, test_account, db
    ):
        from app.domain.services.deposit_service import DepositService

        test_user.webhook_url = "https://webhook.site/test"
        db.commit()

        deposit_service = DepositService(db)
        transaction = deposit_service.create_pending_deposit(
            account_id=test_account.id,
            amount=Decimal("75.00"),
            currency="USD",
        )
        transaction_id = str(transaction.id)

        deposit_service.complete_deposit(
            transaction_id=transaction.id,
            bank_transaction_id="TEST-BANK-ID",
            bank_response="Test success",
        )

        response = client.get(
            f"/webhooks/deliveries?transaction_id={transaction_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["deliveries"]) == 1
        assert all(d["transaction_id"] == transaction_id for d in data["deliveries"])


class TestWebhookRetryMechanism:

    def test_webhook_delivery_created_on_success(self, db, test_account):
        from app.domain.services.deposit_service import DepositService
        from app.infrastructure.repositories.user_repository import UserRepository

        user_repo = UserRepository(db)
        user = user_repo.get_by_id(test_account.user_id)
        user.webhook_url = "https://webhook.site/test"
        db.commit()

        deposit_service = DepositService(db)
        transaction = deposit_service.create_pending_deposit(
            account_id=test_account.id,
            amount=Decimal("100.00"),
            currency="USD",
        )
        deposit_service.complete_deposit(
            transaction_id=transaction.id,
            bank_transaction_id="TEST-BANK-ID",
            bank_response="Test success",
        )

        webhook_repo = WebhookRepository(db)
        deliveries = webhook_repo.get_by_transaction_id(transaction.id)
        assert len(deliveries) == 1
        assert deliveries[0].webhook_url == "https://webhook.site/test"
        assert deliveries[0].status == WebhookDeliveryStatus.PENDING
        assert deliveries[0].attempt_count == 0

    def test_webhook_delivery_created_on_failure(self, db, test_account):
        from app.domain.services.deposit_service import DepositService
        from app.infrastructure.repositories.user_repository import UserRepository

        user_repo = UserRepository(db)
        user = user_repo.get_by_id(test_account.user_id)
        user.webhook_url = "https://webhook.site/test"
        db.commit()

        deposit_service = DepositService(db)
        transaction = deposit_service.create_pending_deposit(
            account_id=test_account.id,
            amount=Decimal("25.00"),
            currency="USD",
        )
        deposit_service.fail_deposit(
            transaction_id=transaction.id,
            error_code="BANK_ERROR",
            error_message="Bank processing failed",
        )

        webhook_repo = WebhookRepository(db)
        deliveries = webhook_repo.get_by_transaction_id(transaction.id)
        assert len(deliveries) == 1
        assert deliveries[0].status == WebhookDeliveryStatus.PENDING

    def test_no_webhook_if_url_not_configured(self, db, test_account):
        from app.domain.services.deposit_service import DepositService

        deposit_service = DepositService(db)
        transaction = deposit_service.create_pending_deposit(
            account_id=test_account.id,
            amount=Decimal("100.00"),
            currency="USD",
        )
        deposit_service.complete_deposit(
            transaction_id=transaction.id,
            bank_transaction_id="TEST-BANK-ID",
            bank_response="Test success",
        )

        webhook_repo = WebhookRepository(db)
        deliveries = webhook_repo.get_by_transaction_id(transaction.id)
        assert len(deliveries) == 0
