"""Shared Fernet encryption utilities for secrets at rest.

Used for LLM API tokens (Phase 6A) and SMTP passwords (Phase 6F).
"""

from cryptography.fernet import Fernet

from src.config import settings
from src.logging_config import get_logger

logger = get_logger(__name__)


def _get_fernet() -> Fernet:
    """Get Fernet instance for token encryption/decryption.

    Raises:
        ValueError: If LLM_ENCRYPTION_KEY is not set.
    """
    if not settings.llm_encryption_key:
        raise ValueError(
            "LLM_ENCRYPTION_KEY is not set. Generate one with: "
            "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    return Fernet(settings.llm_encryption_key.encode())


def encrypt_token(token: str) -> str:
    """Encrypt an API token for storage."""
    return _get_fernet().encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt an API token for use."""
    return _get_fernet().decrypt(encrypted.encode()).decode()


def encrypt_value(value: str) -> str:
    """Encrypt a generic string value for storage (e.g., SMTP password)."""
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    """Decrypt a generic string value for use (e.g., SMTP password)."""
    return _get_fernet().decrypt(encrypted.encode()).decode()


def mask_token(token: str) -> str:
    """Mask a token for display (e.g., 'sk-...a3f2')."""
    if len(token) <= 8:
        return "****"
    return f"{token[:3]}...{token[-4:]}"
