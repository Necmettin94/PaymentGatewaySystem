class TestUserEndpoints:
    def test_get_current_user_profile(self, client, auth_headers, test_user):
        response = client.get(
            "/api/v1/users/me",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_user.id)
        assert data["email"] == test_user.email
        assert data["full_name"] == test_user.full_name
        assert data["is_active"] is True

    def test_get_balance_success(self, client, auth_headers, test_user, db):
        from app.infrastructure.repositories.account_repository import AccountRepository

        account_repo = AccountRepository(db)
        account = account_repo.get_by_user_id(test_user.id)

        response = client.get(
            "/api/v1/users/me/balance",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "balance" in data
        assert data["currency"] == "USD"
        assert data["account_id"] == str(account.id)

    def test_get_transactions_success(self, client, auth_headers, test_user):
        response = client.get(
            "/api/v1/users/me/transactions?skip=0&limit=10",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
