from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_webhook_signature,
    get_password_hash,
    verify_password,
    verify_webhook_signature,
)


class TestPasswordHashing:
    def test_password_hashing(self):

        password = "mysecretpassword"
        hashed = get_password_hash(password)

        assert hashed != password
        assert len(hashed) > 0

    def test_verify_password_correct(self):

        password = "mysecretpassword"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):

        password = "mysecretpassword"
        hashed = get_password_hash(password)

        assert verify_password("wrongpassword", hashed) is False


class TestJWT:

    def test_create_access_token(self):

        data = {"sub": "user123", "email": "test@example.com"}
        token = create_access_token(data)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_access_token(self):

        data = {"sub": "user123", "email": "test@example.com"}
        token = create_access_token(data)

        decoded = decode_access_token(token)

        assert decoded is not None
        assert decoded["sub"] == "user123"
        assert decoded["email"] == "test@example.com"

    def test_decode_invalid_token(self):

        invalid_token = "invalid.token.here"

        decoded = decode_access_token(invalid_token)

        assert decoded is None


class TestWebhookSignature:

    def test_generate_webhook_signature(self):
        payload = '{"transaction_id": "123", "status": "success"}'
        secret = "my-secret-key"

        signature = generate_webhook_signature(payload, secret)

        assert isinstance(signature, str)
        assert len(signature) == 64

    def test_verify_webhook_signature_valid(self):

        payload = '{"transaction_id": "123", "status": "success"}'
        secret = "my-secret-key"

        signature = generate_webhook_signature(payload, secret)
        is_valid = verify_webhook_signature(payload, signature, secret)

        assert is_valid is True

    def test_verify_webhook_signature_invalid(self):
        payload = '{"transaction_id": "123", "status": "success"}'
        secret = "my-secret-key"
        wrong_signature = "wrong-signature-here"

        is_valid = verify_webhook_signature(payload, wrong_signature, secret)

        assert is_valid is False

    def test_verify_webhook_signature_tampered_payload(self):
        original_payload = '{"transaction_id": "123", "status": "success"}'
        secret = "my-secret-key"

        signature = generate_webhook_signature(original_payload, secret)

        tampered_payload = '{"transaction_id": "123", "status": "failed"}'

        is_valid = verify_webhook_signature(tampered_payload, signature, secret)

        assert is_valid is False
