from app.core.security import generate_webhook_signature, verify_webhook_signature


class TestWebhookSignature:

    def test_generate_signature_returns_hex_string(self):
        payload = '{"transaction_id": "123", "status": "SUCCESS"}'
        secret = "test-secret-key"
        signature = generate_webhook_signature(payload, secret)

        assert len(signature) == 64
        assert all(c in "0123456789abcdef" for c in signature)

    def test_same_payload_generates_same_signature(self):
        payload = '{"transaction_id": "123", "status": "SUCCESS"}'
        secret = "test-secret-key"

        sig1 = generate_webhook_signature(payload, secret)
        sig2 = generate_webhook_signature(payload, secret)

        assert sig1 == sig2

    def test_different_payload_generates_different_signature(self):
        secret = "test-secret-key"
        payload1 = '{"transaction_id": "123", "status": "SUCCESS"}'
        payload2 = '{"transaction_id": "456", "status": "FAILED"}'

        sig1 = generate_webhook_signature(payload1, secret)
        sig2 = generate_webhook_signature(payload2, secret)

        assert sig1 != sig2

    def test_different_secret_generates_different_signature(self):
        payload = '{"transaction_id": "123", "status": "SUCCESS"}'
        secret1 = "secret-key-1"
        secret2 = "secret-key-2"

        sig1 = generate_webhook_signature(payload, secret1)
        sig2 = generate_webhook_signature(payload, secret2)

        assert sig1 != sig2

    def test_verify_signature_with_correct_signature_succeeds(self):
        payload = '{"transaction_id": "123", "status": "SUCCESS"}'
        secret = "test-secret-key"

        signature = generate_webhook_signature(payload, secret)
        is_valid = verify_webhook_signature(payload, signature, secret)

        assert is_valid is True

    def test_verify_signature_with_wrong_signature_fails(self):
        payload = '{"transaction_id": "123", "status": "SUCCESS"}'
        secret = "test-secret-key"
        wrong_signature = "0" * 64

        is_valid = verify_webhook_signature(payload, wrong_signature, secret)

        assert is_valid is False

    def test_verify_signature_with_modified_payload_fails(self):
        original_payload = '{"transaction_id": "123", "status": "SUCCESS"}'
        modified_payload = '{"transaction_id": "456", "status": "SUCCESS"}'
        secret = "test-secret-key"

        signature = generate_webhook_signature(original_payload, secret)
        is_valid = verify_webhook_signature(modified_payload, signature, secret)

        assert is_valid is False

    def test_verify_signature_with_wrong_secret_fails(self):
        payload = '{"transaction_id": "123", "status": "SUCCESS"}'
        correct_secret = "test-secret-key"
        wrong_secret = "wrong-secret-key"
        signature = generate_webhook_signature(payload, correct_secret)
        is_valid = verify_webhook_signature(payload, signature, wrong_secret)

        assert is_valid is False

    def test_signature_is_case_sensitive(self):
        payload = '{"transaction_id": "123", "status": "SUCCESS"}'
        secret = "test-secret-key"

        signature = generate_webhook_signature(payload, secret)
        uppercase_signature = signature.upper()

        is_valid = verify_webhook_signature(payload, uppercase_signature, secret)
        assert is_valid is False

    def test_empty_payload_generates_valid_signature(self):
        payload = ""
        secret = "test-secret-key"

        signature = generate_webhook_signature(payload, secret)

        assert len(signature) == 64
        assert verify_webhook_signature(payload, signature, secret) is True

    def test_unicode_payload_generates_valid_signature(self):
        payload = '{"message": "Transaction successful"}'
        secret = "test-secret-key"
        signature = generate_webhook_signature(payload, secret)

        assert len(signature) == 64
        assert verify_webhook_signature(payload, signature, secret) is True

    def test_signature_timing_attack_resistance(self):
        import time

        payload = '{"transaction_id": "123", "status": "SUCCESS"}'
        secret = "test-secret-key"

        correct_sig = generate_webhook_signature(payload, secret)
        wrong_sig1 = "0" * 64
        wrong_sig2 = correct_sig[:-1] + ("0" if correct_sig[-1] != "0" else "1")
        start = time.time()
        for _ in range(1000):
            verify_webhook_signature(payload, wrong_sig1, secret)
        time_wrong = time.time() - start

        start = time.time()
        for _ in range(1000):
            verify_webhook_signature(payload, wrong_sig2, secret)
        time_almost = time.time() - start

        ratio = max(time_wrong, time_almost) / min(time_wrong, time_almost)
        assert ratio < 1.6, f"Timing difference too large: {ratio}"

    def test_whitespace_in_payload_affects_signature(self):
        payload1 = '{"transaction_id":"123","status":"SUCCESS"}'
        payload2 = '{"transaction_id": "123", "status": "SUCCESS"}'
        secret = "test-secret-key"

        sig1 = generate_webhook_signature(payload1, secret)
        sig2 = generate_webhook_signature(payload2, secret)

        assert sig1 != sig2

    def test_known_signature_vector(self):
        payload = "what do ya want for nothing?"
        secret = "Jefe"

        signature = generate_webhook_signature(payload, secret)

        expected = "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"

        assert signature == expected
