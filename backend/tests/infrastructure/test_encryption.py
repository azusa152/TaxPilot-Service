"""Tests for infrastructure/encryption.py — Fernet encryption utilities."""

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from src.infrastructure.encryption import decrypt_token, encrypt_token, mask_token


@pytest.fixture()
def fernet_key() -> str:
    """Generate a valid Fernet key for testing."""
    return Fernet.generate_key().decode()


class TestEncryptDecryptRoundTrip:
    """Encrypt/decrypt should round-trip correctly."""

    @patch("src.infrastructure.encryption.settings")
    def test_round_trip_normal_token(self, mock_settings, fernet_key):
        mock_settings.llm_encryption_key = fernet_key
        token = "sk-abc123def456ghi789"
        encrypted = encrypt_token(token)
        assert encrypted != token
        assert decrypt_token(encrypted) == token

    @patch("src.infrastructure.encryption.settings")
    def test_round_trip_empty_token(self, mock_settings, fernet_key):
        mock_settings.llm_encryption_key = fernet_key
        token = ""
        encrypted = encrypt_token(token)
        assert decrypt_token(encrypted) == token

    @patch("src.infrastructure.encryption.settings")
    def test_round_trip_long_token(self, mock_settings, fernet_key):
        mock_settings.llm_encryption_key = fernet_key
        token = "x" * 1000
        encrypted = encrypt_token(token)
        assert decrypt_token(encrypted) == token

    @patch("src.infrastructure.encryption.settings")
    def test_round_trip_unicode_token(self, mock_settings, fernet_key):
        mock_settings.llm_encryption_key = fernet_key
        token = "token-with-日本語-characters"
        encrypted = encrypt_token(token)
        assert decrypt_token(encrypted) == token


class TestEncryptionKeyMissing:
    """Missing encryption key should raise ValueError."""

    @patch("src.infrastructure.encryption.settings")
    def test_encrypt_raises_without_key(self, mock_settings):
        mock_settings.llm_encryption_key = ""
        with pytest.raises(ValueError, match="LLM_ENCRYPTION_KEY is not set"):
            encrypt_token("some-token")

    @patch("src.infrastructure.encryption.settings")
    def test_decrypt_raises_without_key(self, mock_settings):
        mock_settings.llm_encryption_key = ""
        with pytest.raises(ValueError, match="LLM_ENCRYPTION_KEY is not set"):
            decrypt_token("some-encrypted-data")


class TestMaskToken:
    """Token masking for safe display."""

    def test_mask_long_token(self):
        assert mask_token("sk-abc123def456ghi789") == "sk-...i789"

    def test_mask_short_token(self):
        assert mask_token("abc") == "****"

    def test_mask_exactly_8_chars(self):
        assert mask_token("12345678") == "****"

    def test_mask_9_chars(self):
        assert mask_token("123456789") == "123...6789"

    def test_mask_empty_token(self):
        assert mask_token("") == "****"
