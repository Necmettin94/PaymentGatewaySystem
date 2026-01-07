import json
import time
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.security import generate_webhook_signature
from app.main import app

client = TestClient(app)


def get_current_timestamp() -> int:
    return int(time.time())


class TestWebhookSecurity:
    def test_webhook_without_signature_fails(self):
        payload = {
            "transaction_id": str(uuid4()),
            "status": "SUCCESS",
            "bank_transaction_id": "BANK-123",
            "message": "Transaction successful",
        }

        response = client.post("/webhooks/bank-callback", json=payload)

        assert response.status_code == 422
        assert "field required" in response.text.lower()

    def test_webhook_with_invalid_signature_fails(self):
        payload = {
            "transaction_id": str(uuid4()),
            "status": "SUCCESS",
            "bank_transaction_id": "BANK-123",
            "message": "Transaction successful",
            "timestamp": get_current_timestamp(),
        }

        response = client.post(
            "/webhooks/bank-callback",
            json=payload,
            headers={"X-Bank-Signature": "invalid_signature_12345"},
        )

        assert response.status_code == 401
        assert "Invalid webhook signature" in response.json()["detail"]

    def test_webhook_with_valid_signature_succeeds(self, client, db, test_user):
        from app.config import settings
        from app.core.enums import TransactionStatus, TransactionType
        from app.infrastructure.models.account import Account
        from app.infrastructure.models.transaction import Transaction

        account = db.query(Account).filter(Account.user_id == test_user.id).first()

        transaction = Transaction(
            account_id=account.id,
            transaction_type=TransactionType.DEPOSIT,
            amount=100.00,
            currency="USD",
            status=TransactionStatus.PROCESSING,
        )
        db.add(transaction)
        db.commit()

        payload = {
            "transaction_id": str(transaction.id),
            "status": "SUCCESS",
            "bank_transaction_id": "BANK-TEST-123",
            "message": "Transaction successful",
            "timestamp": get_current_timestamp(),
        }

        payload_str = json.dumps(payload, separators=(",", ":"))
        valid_signature = generate_webhook_signature(payload_str, settings.bank_webhook_secret)

        response = client.post(
            "/webhooks/bank-callback",
            json=payload,
            headers={"X-Bank-Signature": valid_signature},
        )

        assert response.status_code == 200
        assert response.json()["received"] is True
        assert "processed successfully" in response.json()["message"]

    def test_webhook_signature_timing_attack_resistance(self):

        payload = {
            "transaction_id": str(uuid4()),
            "status": "SUCCESS",
            "bank_transaction_id": "BANK-123",
            "message": "Transaction successful",
            "timestamp": get_current_timestamp(),
        }

        wrong_sig = "0" * 64
        start = time.time()
        response1 = client.post(
            "/webhooks/bank-callback",
            json=payload,
            headers={"X-Bank-Signature": wrong_sig},
        )
        time1 = time.time() - start

        from app.config import settings

        payload_str = json.dumps(payload, separators=(",", ":"))
        correct_sig = generate_webhook_signature(payload_str, settings.bank_webhook_secret)
        almost_correct_sig = correct_sig[:-1] + ("0" if correct_sig[-1] != "0" else "1")

        start = time.time()
        response2 = client.post(
            "/webhooks/bank-callback",
            json=payload,
            headers={"X-Bank-Signature": almost_correct_sig},
        )
        time2 = time.time() - start

        assert response1.status_code == 401
        assert response2.status_code == 401

        assert abs(time1 - time2) < 0.1

    def test_webhook_signature_with_modified_payload_fails(self, client, db, test_user):
        from app.config import settings
        from app.core.enums import TransactionStatus, TransactionType
        from app.infrastructure.models.account import Account
        from app.infrastructure.models.transaction import Transaction

        account = db.query(Account).filter(Account.user_id == test_user.id).first()

        transaction = Transaction(
            account_id=account.id,
            transaction_type=TransactionType.DEPOSIT,
            amount=100.00,
            currency="USD",
            status=TransactionStatus.PROCESSING,
        )
        db.add(transaction)
        db.commit()

        original_payload = {
            "transaction_id": str(transaction.id),
            "status": "SUCCESS",
            "bank_transaction_id": "BANK-TEST-123",
            "message": "Transaction successful",
            "timestamp": get_current_timestamp(),
        }

        payload_str = json.dumps(original_payload, separators=(",", ":"))
        valid_signature = generate_webhook_signature(payload_str, settings.bank_webhook_secret)

        modified_payload = original_payload.copy()
        modified_payload["transaction_id"] = str(uuid4())

        response = client.post(
            "/webhooks/bank-callback",
            json=modified_payload,
            headers={"X-Bank-Signature": valid_signature},
        )

        assert response.status_code == 401
        assert "Invalid webhook signature" in response.json()["detail"]

    def test_webhook_signature_case_sensitivity(self):
        from app.config import settings

        payload = {
            "transaction_id": str(uuid4()),
            "status": "SUCCESS",
            "bank_transaction_id": "BANK-123",
            "message": "Transaction successful",
            "timestamp": get_current_timestamp(),
        }

        payload_str = json.dumps(payload, separators=(",", ":"))
        correct_sig = generate_webhook_signature(payload_str, settings.bank_webhook_secret)

        uppercase_sig = correct_sig.upper()

        response = client.post(
            "/webhooks/bank-callback",
            json=payload,
            headers={"X-Bank-Signature": uppercase_sig},
        )

        if correct_sig.islower():
            assert response.status_code == 401
