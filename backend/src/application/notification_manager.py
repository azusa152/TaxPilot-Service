"""NotificationManager - fire-and-forget email orchestration with retry logic.

Failures are logged but never block the Evolution Pipeline.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import NotificationEvent
from src.infrastructure import email_templates
from src.infrastructure.models import NotificationConfig, NotificationLog
from src.infrastructure.notification_service import NotificationService, SmtpNotifier

logger = logging.getLogger(__name__)


class NotificationManager:
    """Orchestrates notifications with retry logic and fire-and-forget pattern."""

    # High-priority events retry up to 3 times with exponential backoff
    HIGH_PRIORITY_EVENTS = {
        NotificationEvent.REGULATION_CHANGE_DETECTED,
        NotificationEvent.FORMULA_READY_FOR_REVIEW,
        NotificationEvent.RUN_FAILED,
    }
    MAX_RETRIES = 3

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_active_config(self) -> NotificationConfig | None:
        """Fetch active notification configuration.

        Returns:
            Active NotificationConfig or None if notifications are disabled.
        """
        result = await self.db.execute(
            select(NotificationConfig).where(NotificationConfig.is_active == True)
        )
        return result.scalars().first()

    def _is_event_enabled(self, config: NotificationConfig, event: NotificationEvent) -> bool:
        """Check if an event type is enabled in configuration.

        Args:
            config: Active notification configuration
            event: Event type to check

        Returns:
            True if event is in enabled_events list
        """
        return event.value in config.enabled_events

    def _is_high_priority(self, event: NotificationEvent) -> bool:
        """Check if an event is high-priority (requires retry).

        Args:
            event: Event type to check

        Returns:
            True if event is in HIGH_PRIORITY_EVENTS set
        """
        return event in self.HIGH_PRIORITY_EVENTS

    async def _create_log_entry(
        self,
        event: NotificationEvent,
        evolution_run_id: int | None,
        recipient_emails: list[str],
        subject: str,
        success: bool,
        error_message: str | None = None,
        retry_count: int = 0,
    ) -> NotificationLog:
        """Create a notification log entry.

        Args:
            event: Notification event type
            evolution_run_id: Associated evolution run ID (if applicable)
            recipient_emails: List of recipients
            subject: Email subject
            success: Whether notification was sent successfully
            error_message: Error details if failed
            retry_count: Number of retry attempts

        Returns:
            Created NotificationLog record
        """
        log = NotificationLog(
            event=event.value,
            evolution_run_id=evolution_run_id,
            recipient_emails=recipient_emails,
            subject=subject,
            sent_at=datetime.now(timezone.utc),
            success=success,
            error_message=error_message,
            retry_count=retry_count,
        )
        self.db.add(log)
        await self.db.commit()
        return log

    async def _send_with_retry(
        self,
        notifier: NotificationService,
        subject: str,
        html_body: str,
        text_body: str,
        recipient_emails: list[str],
        event: NotificationEvent,
        evolution_run_id: int | None,
    ) -> bool:
        """Send notification with exponential backoff retry for high-priority events.

        Args:
            notifier: Configured notification service
            subject: Email subject
            html_body: HTML message body
            text_body: Plain text fallback
            recipient_emails: List of recipients
            event: Event type (determines retry behavior)
            evolution_run_id: Associated run ID (for logging)

        Returns:
            True if eventually sent successfully, False otherwise
        """
        max_attempts = self.MAX_RETRIES if self._is_high_priority(event) else 1

        for attempt in range(max_attempts):
            success = await notifier.send(
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                recipient_emails=recipient_emails,
            )

            if success:
                await self._create_log_entry(
                    event=event,
                    evolution_run_id=evolution_run_id,
                    recipient_emails=recipient_emails,
                    subject=subject,
                    success=True,
                    retry_count=attempt,
                )
                return True

            # If not the last attempt, wait with exponential backoff
            if attempt < max_attempts - 1:
                backoff_seconds = 2**attempt
                logger.warning(
                    f"Notification failed (attempt {attempt + 1}/{max_attempts}). "
                    f"Retrying in {backoff_seconds}s... event={event.value}"
                )
                await asyncio.sleep(backoff_seconds)

        # All attempts failed
        error_message = f"Failed after {max_attempts} attempts"
        await self._create_log_entry(
            event=event,
            evolution_run_id=evolution_run_id,
            recipient_emails=recipient_emails,
            subject=subject,
            success=False,
            error_message=error_message,
            retry_count=max_attempts - 1,
        )
        logger.error(
            f"Notification permanently failed: event={event.value}, "
            f"subject='{subject}', attempts={max_attempts}"
        )
        return False

    async def notify(
        self,
        event: NotificationEvent,
        evolution_run_id: int | None = None,
        **template_kwargs,
    ) -> None:
        """Fire-and-forget notification sender.

        This method NEVER raises exceptions - all errors are logged.

        Args:
            event: Notification event type
            evolution_run_id: Associated evolution run ID (optional)
            **template_kwargs: Arguments for the email template function

        Returns:
            None (fire-and-forget)
        """
        try:
            # Check if notifications are enabled
            config = await self._get_active_config()
            if not config:
                logger.debug("Notifications disabled - skipping")
                return

            # Check if this event type is enabled
            if not self._is_event_enabled(config, event):
                logger.debug(f"Event {event.value} not enabled - skipping")
                return

            # Get template function
            template_func = getattr(email_templates, event.value.lower(), None)
            if not template_func:
                logger.error(f"No template function found for event: {event.value}")
                return

            # Generate email content
            subject, html_body, text_body = template_func(**template_kwargs)

            # Create notifier from config
            notifier = SmtpNotifier.from_config(config)

            # Send with retry logic
            await self._send_with_retry(
                notifier=notifier,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                recipient_emails=config.recipient_emails,
                event=event,
                evolution_run_id=evolution_run_id,
            )

        except Exception as e:
            # Fire-and-forget: log but never propagate
            logger.error(
                f"Notification handler failed: event={event.value}, error={e}",
                exc_info=True,
            )

    # Convenience methods for each event type

    async def notify_regulation_change_detected(
        self,
        page_name: str,
        page_url: str,
        snapshot_id: int,
        dashboard_url: str,
    ) -> None:
        """Send REGULATION_CHANGE_DETECTED notification."""
        await self.notify(
            event=NotificationEvent.REGULATION_CHANGE_DETECTED,
            evolution_run_id=None,
            page_name=page_name,
            page_url=page_url,
            snapshot_id=snapshot_id,
            dashboard_url=dashboard_url,
        )

    async def notify_formula_ready_for_review(
        self,
        run_id: int,
        function_name: str,
        change_summary: str,
        dashboard_url: str,
    ) -> None:
        """Send FORMULA_READY_FOR_REVIEW notification (high priority)."""
        await self.notify(
            event=NotificationEvent.FORMULA_READY_FOR_REVIEW,
            evolution_run_id=run_id,
            run_id=run_id,
            function_name=function_name,
            change_summary=change_summary,
            dashboard_url=dashboard_url,
        )

    async def notify_formula_activated(
        self,
        run_id: int,
        function_name: str,
        version: str,
        decision: str,
        dashboard_url: str,
    ) -> None:
        """Send FORMULA_ACTIVATED notification."""
        await self.notify(
            event=NotificationEvent.FORMULA_ACTIVATED,
            evolution_run_id=run_id,
            function_name=function_name,
            version=version,
            decision=decision,
            dashboard_url=dashboard_url,
        )

    async def notify_formula_regenerating(
        self,
        run_id: int,
        attempt: int,
        max_attempts: int,
        hints: str | None,
        dashboard_url: str,
    ) -> None:
        """Send FORMULA_REGENERATING notification."""
        await self.notify(
            event=NotificationEvent.FORMULA_REGENERATING,
            evolution_run_id=run_id,
            run_id=run_id,
            attempt=attempt,
            max_attempts=max_attempts,
            hints=hints,
            dashboard_url=dashboard_url,
        )

    async def notify_run_failed(
        self,
        run_id: int,
        failed_step: str,
        error: str,
        dashboard_url: str,
    ) -> None:
        """Send RUN_FAILED notification (high priority)."""
        await self.notify(
            event=NotificationEvent.RUN_FAILED,
            evolution_run_id=run_id,
            run_id=run_id,
            failed_step=failed_step,
            error=error,
            dashboard_url=dashboard_url,
        )

    async def notify_deferred_reminder(
        self,
        deferred_count: int,
        deferred_runs: list[dict],
        dashboard_url: str,
    ) -> None:
        """Send DEFERRED_REMINDER weekly digest."""
        await self.notify(
            event=NotificationEvent.DEFERRED_REMINDER,
            evolution_run_id=None,
            deferred_count=deferred_count,
            deferred_runs=deferred_runs,
            dashboard_url=dashboard_url,
        )
