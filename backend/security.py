import base64
import binascii
import os
from cryptography.fernet import Fernet, InvalidToken

ENCRYPTION_PREFIX_V1 = "enc:v1:"


def _get_fernet() -> Fernet:
    """
    Retrieves the configured Fernet instance using PLAID_TOKEN_ENCRYPTION_KEY.
    Raises RuntimeError if key is missing, or ValueError if key format is invalid.
    """
    key = os.getenv("PLAID_TOKEN_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("PLAID_TOKEN_ENCRYPTION_KEY environment variable is not configured.")
    try:
        return Fernet(key.strip().encode("utf-8"))
    except (ValueError, binascii.Error) as exc:
        raise ValueError(
            "PLAID_TOKEN_ENCRYPTION_KEY is invalid. Expected a 32-byte base64-urlsafe string."
        ) from exc


def encrypt_token(token: str) -> str:
    """
    Encrypts a plaintext Plaid access token using Fernet authenticated encryption.
    Returns version-prefixed ciphertext: 'enc:v1:<Fernet token>'
    """
    if not token:
        raise ValueError("Cannot encrypt empty token.")
    fernet = _get_fernet()
    ciphertext = fernet.encrypt(token.encode("utf-8")).decode("utf-8")
    return f"{ENCRYPTION_PREFIX_V1}{ciphertext}"


def decrypt_token(encrypted_token: str) -> str:
    """
    Decrypts an encrypted Plaid access token.
    Runtime decryption is STRICT: accepts only 'enc:v1:' prefixed tokens.
    Raises ValueError or InvalidToken on malformed, unversioned, or invalid tokens.
    """
    if not encrypted_token:
        raise ValueError("Cannot decrypt empty token.")
    if not encrypted_token.startswith(ENCRYPTION_PREFIX_V1):
        raise ValueError("Stored token does not match supported encryption version 'enc:v1:'.")

    payload = encrypted_token[len(ENCRYPTION_PREFIX_V1):]
    fernet = _get_fernet()
    decrypted_bytes = fernet.decrypt(payload.encode("utf-8"))
    return decrypted_bytes.decode("utf-8")


def _decode_legacy_token(stored: str) -> str:
    """
    Migration-only helper: strictly validates and decodes historical Base64 tokens.
    Raises ValueError on invalid Base64 alphabet, bad padding, invalid UTF-8, or empty result.
    """
    if not stored:
        raise ValueError("Cannot decode empty legacy token.")
    if len(stored) % 4 != 0:
        raise ValueError("Malformed legacy Base64 token data.")
    try:
        raw_bytes = base64.b64decode(stored.encode("utf-8"), validate=True)
        if base64.b64encode(raw_bytes).decode("utf-8") != stored:
            raise ValueError("Malformed legacy Base64 token data.")
        plaintext = raw_bytes.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Malformed legacy Base64 token data.") from exc

    if not plaintext:
        raise ValueError("Legacy token decoded to empty string.")
    return plaintext