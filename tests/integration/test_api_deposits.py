from uuid import uuid4


class TestDepositEndpoints:
    def test_create_deposit_without_idempotency_key_fails(self, client, auth_headers):
        response = client.post(
            "/api/v1/deposits",
            headers=auth_headers,
            json={
                "amount": 100.00,
                "currency": "USD",
            },
        )

        assert response.status_code == 400
        assert "idempotency" in response.json()["message"].lower()
        assert "required" in response.json()["message"].lower()

    def test_create_deposit_success(self, client, auth_headers):
        headers = {
            **auth_headers,
            "Idempotency-Key": str(uuid4()),
        }

        response = client.post(
            "/api/v1/deposits",
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
        assert float(data["amount"]) == 100.00

    def test_idempotency_returns_same_response(self, client, auth_headers):
        idempotency_key = str(uuid4())
        headers = {
            **auth_headers,
            "Idempotency-Key": idempotency_key,
        }

        response1 = client.post(
            "/api/v1/deposits",
            headers=headers,
            json={
                "amount": 100.00,
                "currency": "USD",
            },
        )

        response2 = client.post(
            "/api/v1/deposits",
            headers=headers,
            json={
                "amount": 100.00,
                "currency": "USD",
            },
        )

        assert response1.status_code == 202
        assert response2.status_code == 202

        assert response1.json()["id"] == response2.json()["id"]

    def test_get_deposit_success(self, client, auth_headers):
        headers = {
            **auth_headers,
            "Idempotency-Key": str(uuid4()),
        }

        create_response = client.post(
            "/api/v1/deposits",
            headers=headers,
            json={
                "amount": 100.00,
                "currency": "USD",
            },
        )

        transaction_id = create_response.json()["id"]

        response = client.get(
            f"/api/v1/deposits/{transaction_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == transaction_id
        assert float(data["amount"]) == 100.00

    def test_list_deposits(self, client, auth_headers):
        for _ in range(3):
            headers = {
                **auth_headers,
                "Idempotency-Key": str(uuid4()),
            }
            client.post(
                "/api/v1/deposits",
                headers=headers,
                json={
                    "amount": 50.00,
                    "currency": "USD",
                },
            )

        response = client.get(
            "/api/v1/deposits?skip=0&limit=10",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 3
