"""
Unit tests for Plaid token authenticated encryption helper (backend/security.py).
"""

import base64
import os
import pytest
from cryptography.fernet import Fernet, InvalidToken

from backend.security import (
    ENCRYPTION_PREFIX_V1,
    _decode_legacy_token,
    _get_fernet,
    decrypt_token,
    encrypt_token,
)


VALID_TEST_KEY_1 = "bZ2eZ7L_G4r4yQ7F2U_8sK3yT6xV1wA5bC9dE3fG7hI="
VALID_TEST_KEY_2 = "4m-rF7S8_H2k3P9L1a5D6f7G8h9J0k1L2m3N4p5Q6r8="


@pytest.fixture(autouse=True)
def ensure_default_test_key(monkeypatch):
    monkeypatch.setenv("PLAID_TOKEN_ENCRYPTION_KEY", VALID_TEST_KEY_1)


def test_encrypt_decrypt_round_trip():
    plaintext = "access-sandbox-9999-aaaa-bbbb-cccc"
    encrypted = encrypt_token(plaintext)
    decrypted = decrypt_token(encrypted)
    assert decrypted == plaintext


def test_ciphertext_has_enc_v1_prefix():
    encrypted = encrypt_token("access-test-token")
    assert encrypted.startswith(ENCRYPTION_PREFIX_V1)
    # Payload after prefix should be valid base64-urlsafe
    payload = encrypted[len(ENCRYPTION_PREFIX_V1):]
    assert len(payload) > 50


def test_ciphertext_differs_from_plaintext():
    plaintext = "access-secret-token-xyz"
    encrypted = encrypt_token(plaintext)
    assert encrypted != plaintext
    assert plaintext not in encrypted


def test_encrypting_same_plaintext_twice_yields_different_stored_strings():
    plaintext = "access-deterministic-check"
    enc1 = encrypt_token(plaintext)
    enc2 = encrypt_token(plaintext)
    assert enc1 != enc2
    assert decrypt_token(enc1) == plaintext
    assert decrypt_token(enc2) == plaintext


def test_tampered_ciphertext_rejected():
    encrypted = encrypt_token("access-tamper-check")
    # Mutate a character in the ciphertext payload
    prefix = ENCRYPTION_PREFIX_V1
    payload = encrypted[len(prefix):]
    tampered_char = "B" if payload[-5] == "A" else "A"
    tampered = prefix + payload[:-5] + tampered_char + payload[-4:]

    with pytest.raises(InvalidToken):
        decrypt_token(tampered)


def test_truncated_ciphertext_rejected():
    encrypted = encrypt_token("access-truncate-check")
    truncated = encrypted[:-10]
    with pytest.raises(InvalidToken):
        decrypt_token(truncated)


def test_wrong_key_rejected(monkeypatch):
    encrypted = encrypt_token("access-key-check")
    # Switch to different valid key
    monkeypatch.setenv("PLAID_TOKEN_ENCRYPTION_KEY", VALID_TEST_KEY_2)
    with pytest.raises(InvalidToken):
        decrypt_token(encrypted)


def test_missing_key_rejected(monkeypatch):
    monkeypatch.delenv("PLAID_TOKEN_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="PLAID_TOKEN_ENCRYPTION_KEY environment variable is not configured"):
        encrypt_token("access-missing-key")

    with pytest.raises(RuntimeError, match="PLAID_TOKEN_ENCRYPTION_KEY environment variable is not configured"):
        decrypt_token("enc:v1:gAAAAAB...")


def test_invalid_key_rejected(monkeypatch):
    monkeypatch.setenv("PLAID_TOKEN_ENCRYPTION_KEY", "not-a-valid-fernet-key")
    with pytest.raises(ValueError, match="PLAID_TOKEN_ENCRYPTION_KEY is invalid"):
        encrypt_token("access-invalid-key")


def test_empty_plaintext_encryption_rejected():
    with pytest.raises(ValueError, match="Cannot encrypt empty token"):
        encrypt_token("")


def test_empty_stored_decryption_rejected():
    with pytest.raises(ValueError, match="Cannot decrypt empty token"):
        decrypt_token("")


def test_legacy_base64_rejected_by_normal_runtime_decrypt():
    legacy_base64 = base64.b64encode(b"access-sandbox-legacy").decode("utf-8")
    with pytest.raises(ValueError, match="does not match supported encryption version 'enc:v1:'"):
        decrypt_token(legacy_base64)


def test_unsupported_enc_version_rejected():
    unsupported = "enc:v2:some_ciphertext_here"
    with pytest.raises(ValueError, match="does not match supported encryption version 'enc:v1:'"):
        decrypt_token(unsupported)


def test_strict_legacy_decoder_accepts_valid_base64():
    raw_plaintext = "access-sandbox-old-token"
    encoded = base64.b64encode(raw_plaintext.encode("utf-8")).decode("utf-8")
    decoded = _decode_legacy_token(encoded)
    assert decoded == raw_plaintext


def test_strict_legacy_decoder_rejects_malformed_base64():
    # Non-base64 characters
    with pytest.raises(ValueError, match="Malformed legacy Base64 token data"):
        _decode_legacy_token("!!!NOT_VALID_BASE64!!!")

    # Bad padding
    with pytest.raises(ValueError, match="Malformed legacy Base64 token data"):
        _decode_legacy_token("YWNjZXNzLXRva2Vu=")  # Incorrect padding length


def test_strict_legacy_decoder_rejects_empty():
    with pytest.raises(ValueError, match="Cannot decode empty legacy token"):
        _decode_legacy_token("")

    # Empty payload base64
    empty_b64 = base64.b64encode(b"").decode("utf-8")
    with pytest.raises(ValueError, match="Cannot decode empty legacy token"):
        _decode_legacy_token(empty_b64)
