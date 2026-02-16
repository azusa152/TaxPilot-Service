"""NotificationService interface and SMTP implementation.

Protocol-based design allows future Slack/webhook adapters without pipeline changes.
"""

import logging
from typing import Protocol

import aiosmtplib
from email.message import EmailMessage

from src.infrastructure.models import NotificationConfig

logger = logging.getLogger(__name__)


class NotificationService(Protocol):
    """Protocol for sending notifications via different channels."""

    async def send(
        self,
        subject: str,
        html_body: str,
        text_body: str,
        recipient_emails: list[str],
    ) -> bool:
        """Send a notification.

        Args:
            subject: Email subject line
            html_body: HTML-formatted message body
            text_body: Plain text fallback body
            recipient_emails: List of recipient email addresses

        Returns:
            True if sent successfully, False otherwise
        """
        ...


class SmtpNotifier:
    """SMTP email notifier implementation."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        sender_email: str,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.sender_email = sender_email

    @classmethod
    def from_config(cls, config: NotificationConfig) -> "SmtpNotifier":
        """Create notifier from database configuration.

        Args:
            config: NotificationConfig record with encrypted password

        Returns:
            Configured SmtpNotifier instance
        """
        from src.infrastructure.encryption import decrypt_value

        decrypted_password = decrypt_value(config.encrypted_smtp_password)

        return cls(
            smtp_host=config.smtp_host,
            smtp_port=config.smtp_port,
            smtp_user=config.smtp_user,
            smtp_password=decrypted_password,
            sender_email=config.sender_email,
        )

    async def send(
        self,
        subject: str,
        html_body: str,
        text_body: str,
        recipient_emails: list[str],
    ) -> bool:
        """Send email via SMTP with HTML and text alternatives.

        Args:
            subject: Email subject line
            html_body: HTML-formatted message body
            text_body: Plain text fallback body
            recipient_emails: List of recipient email addresses

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            message = EmailMessage()
            message["Subject"] = subject
            message["From"] = self.sender_email
            message["To"] = ", ".join(recipient_emails)

            # Set plain text content
            message.set_content(text_body)

            # Add HTML alternative
            message.add_alternative(html_body, subtype="html")

            # Send via SMTP
            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_password,
                start_tls=True,
            )

            logger.info(
                f"Email sent successfully: subject='{subject}', recipients={recipient_emails}"
            )
            return True

        except aiosmtplib.SMTPException as e:
            logger.error(
                f"SMTP error sending email: subject='{subject}', error={e}",
                exc_info=True,
            )
            return False

        except Exception as e:
            logger.error(
                f"Unexpected error sending email: subject='{subject}', error={e}",
                exc_info=True,
            )
            return False
