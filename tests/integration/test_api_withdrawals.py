from decimal import Decimal
from uuid import uuid4


class TestWithdrawalEndpoints:
    def test_create_withdrawal_insufficient_balance_fails(
        self, client, auth_headers, db, test_user
    ):
        headers = {
            **auth_headers,
            "Idempotency-Key": str(uuid4()),
        }

        response = client.post(
            "/api/v1/withdrawals",
            headers=headers,
            json={
                "amount": 9999.00,
                "currency": "USD",
            },
        )

        assert response.status_code == 400
        assert "Insufficient balance" in response.json()["detail"]

    def test_create_withdrawal_success(self, client, auth_headers, db, test_user_with_balance):
        user, account = test_user_with_balance

        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "rich@example.com",
                "password": "password123",
            },
        )

        token = login_response.json()["access_token"]
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": str(uuid4()),
        }

        response = client.post(
            "/api/v1/withdrawals",
            headers=headers,
            json={
                "amount": 100.00,
                "currency": "USD",
            },
        )

        assert response.status_code == 202
        data = response.json()
        assert "id" in data
        assert data["status"] == "PENDING"

        db.refresh(account)
        assert account.balance == Decimal("1000.00")

    def test_get_withdrawal_success(self, client, auth_headers, db, test_user_with_balance):
        user, account = test_user_with_balance

        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "rich@example.com",
                "password": "password123",
            },
        )

        token = login_response.json()["access_token"]
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": str(uuid4()),
        }

        create_response = client.post(
            "/api/v1/withdrawals",
            headers=headers,
            json={
                "amount": 50.00,
                "currency": "USD",
            },
        )

        transaction_id = create_response.json()["id"]

        response = client.get(
            f"/api/v1/withdrawals/{transaction_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == transaction_id
        assert float(data["amount"]) == 50.00
