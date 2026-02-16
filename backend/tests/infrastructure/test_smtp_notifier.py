"""Tests for SmtpNotifier with mocked aiosmtplib."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import aiosmtplib

from src.infrastructure.models import NotificationConfig
from src.infrastructure.notification_service import SmtpNotifier


@pytest.fixture
def notification_config():
    """Create a mock notification configuration."""
    config = MagicMock(spec=NotificationConfig)
    config.smtp_host = "smtp.example.com"
    config.smtp_port = 587
    config.smtp_user = "test@example.com"
    config.encrypted_smtp_password = "encrypted_password_blob"
    config.sender_email = "noreply@taxpilot.com"
    return config


@pytest.fixture
def smtp_notifier():
    """Create an SmtpNotifier instance."""
    return SmtpNotifier(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="test@example.com",
        smtp_password="decrypted_password",
        sender_email="noreply@taxpilot.com",
    )


class TestSmtpNotifierCreation:
    """Test SmtpNotifier instantiation and factory methods."""

    def test_direct_instantiation(self):
        """Should create notifier with direct parameters."""
        notifier = SmtpNotifier(
            smtp_host="smtp.gmail.com",
            smtp_port=465,
            smtp_user="user@gmail.com",
            smtp_password="app_password",
            sender_email="noreply@app.com",
        )

        assert notifier.smtp_host == "smtp.gmail.com"
        assert notifier.smtp_port == 465
        assert notifier.smtp_user == "user@gmail.com"
        assert notifier.smtp_password == "app_password"
        assert notifier.sender_email == "noreply@app.com"

    @patch("src.infrastructure.encryption.decrypt_value")
    def test_from_config_factory(self, mock_decrypt, notification_config):
        """Should create notifier from NotificationConfig with decrypted password."""
        mock_decrypt.return_value = "decrypted_password"

        notifier = SmtpNotifier.from_config(notification_config)

        assert notifier.smtp_host == "smtp.example.com"
        assert notifier.smtp_port == 587
        assert notifier.smtp_user == "test@example.com"
        assert notifier.smtp_password == "decrypted_password"
        assert notifier.sender_email == "noreply@taxpilot.com"

        # Verify decryption was called
        mock_decrypt.assert_called_once_with("encrypted_password_blob")


@pytest.mark.asyncio
class TestSmtpNotifierSend:
    """Test SmtpNotifier.send() with mocked SMTP connection."""

    @patch("src.infrastructure.notification_service.aiosmtplib.send")
    async def test_successful_send(self, mock_smtp_send, smtp_notifier):
        """Should send email successfully and return True."""
        mock_smtp_send.return_value = None  # Successful send returns None

        result = await smtp_notifier.send(
            subject="Test Subject",
            html_body="<html><body>Test HTML</body></html>",
            text_body="Test plain text",
            recipient_emails=["admin1@example.com", "admin2@example.com"],
        )

        assert result is True

        # Verify aiosmtplib.send was called
        mock_smtp_send.assert_called_once()
        call_kwargs = mock_smtp_send.call_args.kwargs

        assert call_kwargs["hostname"] == "smtp.example.com"
        assert call_kwargs["port"] == 587
        assert call_kwargs["username"] == "test@example.com"
        assert call_kwargs["password"] == "decrypted_password"
        assert call_kwargs["start_tls"] is True

        # Verify message structure
        message = mock_smtp_send.call_args.args[0]
        assert message["Subject"] == "Test Subject"
        assert message["From"] == "noreply@taxpilot.com"
        assert message["To"] == "admin1@example.com, admin2@example.com"

    @patch("src.infrastructure.notification_service.aiosmtplib.send")
    async def test_smtp_connection_failure(self, mock_smtp_send, smtp_notifier):
        """Should return False on SMTP connection failure."""
        mock_smtp_send.side_effect = aiosmtplib.SMTPConnectError("Connection refused")

        result = await smtp_notifier.send(
            subject="Test Subject",
            html_body="<html>Test</html>",
            text_body="Test",
            recipient_emails=["admin@example.com"],
        )

        assert result is False

    @patch("src.infrastructure.notification_service.aiosmtplib.send")
    async def test_smtp_authentication_failure(self, mock_smtp_send, smtp_notifier):
        """Should return False on SMTP authentication failure."""
        mock_smtp_send.side_effect = aiosmtplib.SMTPAuthenticationError(
            535, "Authentication failed"
        )

        result = await smtp_notifier.send(
            subject="Test Subject",
            html_body="<html>Test</html>",
            text_body="Test",
            recipient_emails=["admin@example.com"],
        )

        assert result is False

    @patch("src.infrastructure.notification_service.aiosmtplib.send")
    async def test_smtp_tls_error(self, mock_smtp_send, smtp_notifier):
        """Should return False on TLS handshake failure."""
        mock_smtp_send.side_effect = aiosmtplib.SMTPException("TLS handshake failed")

        result = await smtp_notifier.send(
            subject="Test Subject",
            html_body="<html>Test</html>",
            text_body="Test",
            recipient_emails=["admin@example.com"],
        )

        assert result is False

    @patch("src.infrastructure.notification_service.aiosmtplib.send")
    async def test_unexpected_exception(self, mock_smtp_send, smtp_notifier):
        """Should return False on unexpected exceptions."""
        mock_smtp_send.side_effect = RuntimeError("Unexpected error")

        result = await smtp_notifier.send(
            subject="Test Subject",
            html_body="<html>Test</html>",
            text_body="Test",
            recipient_emails=["admin@example.com"],
        )

        assert result is False

    @patch("src.infrastructure.notification_service.aiosmtplib.send")
    async def test_html_and_text_alternatives(self, mock_smtp_send, smtp_notifier):
        """Should create message with both HTML and plain text parts."""
        mock_smtp_send.return_value = None

        html_content = "<html><body><h1>Test</h1></body></html>"
        text_content = "Test plain text version"

        await smtp_notifier.send(
            subject="Test",
            html_body=html_content,
            text_body=text_content,
            recipient_emails=["admin@example.com"],
        )

        # Get the message that was sent
        message = mock_smtp_send.call_args.args[0]

        # Message should be multipart (text + html)
        assert message.is_multipart()

        # Get the parts
        parts = list(message.walk())
        # parts[0] is the container, parts[1] is text, parts[2] is html
        assert len(parts) >= 2

    @patch("src.infrastructure.notification_service.aiosmtplib.send")
    async def test_multiple_recipients(self, mock_smtp_send, smtp_notifier):
        """Should send to multiple recipients in To: header."""
        mock_smtp_send.return_value = None

        recipients = [
            "admin1@example.com",
            "admin2@example.com",
            "admin3@example.com",
        ]

        await smtp_notifier.send(
            subject="Test",
            html_body="<html>Test</html>",
            text_body="Test",
            recipient_emails=recipients,
        )

        message = mock_smtp_send.call_args.args[0]
        assert message["To"] == "admin1@example.com, admin2@example.com, admin3@example.com"

    @patch("src.infrastructure.notification_service.aiosmtplib.send")
    async def test_unicode_subject_and_body(self, mock_smtp_send, smtp_notifier):
        """Should handle Unicode characters in subject and body."""
        mock_smtp_send.return_value = None

        result = await smtp_notifier.send(
            subject="テスト Subject with 日本語",
            html_body="<html><body>Japanese: 日本語</body></html>",
            text_body="Japanese: 日本語",
            recipient_emails=["admin@example.com"],
        )

        assert result is True
        message = mock_smtp_send.call_args.args[0]
        assert "日本語" in message["Subject"]
