"""Cryptographic Security Service for Payaam.

Provides AES-128 CBC / Fernet symmetric encryption and decryption for user-connected
credentials (e.g. BYO-SMTP passwords) at rest in DynamoDB.
"""

import base64
import hashlib
import logging
from typing import Optional
from cryptography.fernet import Fernet
from src.config import settings

logger = logging.getLogger("payaam.services.crypto")


def _get_fernet_instance(custom_key: Optional[str] = None) -> Fernet:
    """Returns a Fernet instance using configured key or a derived fallback."""
    raw_key = custom_key or settings.APP_ENCRYPTION_KEY
    if raw_key:
        try:
            return Fernet(raw_key.encode("utf-8") if isinstance(raw_key, str) else raw_key)
        except Exception as exc:
            logger.warning(f"Configured APP_ENCRYPTION_KEY invalid ({exc}), deriving fallback.")

    # Safe deterministic fallback derived from AWS credentials / system seed
    seed = (settings.AWS_ACCESS_KEY_ID or "payaam-secure-salt-2026").encode("utf-8")
    derived_32 = hashlib.sha256(seed).digest()
    fernet_key = base64.urlsafe_b64encode(derived_32)
    return Fernet(fernet_key)


def encrypt_secret(plain_text: str, key: Optional[str] = None) -> str:
    """Encrypts a sensitive string (e.g. SMTP password) into a base64 ciphertext."""
    if not plain_text:
        return ""
    fernet = _get_fernet_instance(key)
    encrypted = fernet.encrypt(plain_text.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_secret(cipher_text: str, key: Optional[str] = None) -> str:
    """Decrypts a base64 ciphertext back to plain text."""
    if not cipher_text:
        return ""
    try:
        fernet = _get_fernet_instance(key)
        decrypted = fernet.decrypt(cipher_text.encode("utf-8"))
        return decrypted.decode("utf-8")
    except Exception as exc:
        logger.error(f"Failed to decrypt secret: {exc}")
        raise ValueError("Decryption failed. Invalid ciphertext or encryption key.") from exc


def generate_new_key() -> str:
    """Generates a fresh 32-byte url-safe base64 Fernet key."""
    return Fernet.generate_key().decode("utf-8")
