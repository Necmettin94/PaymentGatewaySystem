class TestAuthEndpoints:
    def test_register_user_success(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@example.com",
                "full_name": "New User",
                "password": "password123",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert data["user"]["email"] == "newuser@example.com"
        assert data["user"]["full_name"] == "New User"

    def test_register_duplicate_email_fails(self, client, test_user):
        # FIXME: make email variable to avoid hardcoding
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "full_name": "Duplicate User",
                "password": "password123",
            },
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_login_success(self, client, test_user):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "password123",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password_fails(self, client, test_user):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "wrongpassword",
            },
        )

        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]

    def test_login_nonexistent_user_fails(self, client):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "ghost@example.com",
                "password": "password123",
            },
        )

        assert response.status_code == 401
