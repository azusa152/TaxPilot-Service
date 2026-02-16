"""Tests for NotificationManager with mock SMTP."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.application.notification_manager import NotificationManager
from src.domain.enums import NotificationEvent
from src.infrastructure.models import NotificationConfig, NotificationLog


@pytest.fixture
async def notification_config(db):
    """Create an active notification configuration."""
    config = NotificationConfig(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="test@example.com",
        encrypted_smtp_password="encrypted_password_blob",
        sender_email="noreply@taxpilot.com",
        recipient_emails=["admin1@example.com", "admin2@example.com"],
        enabled_events=[
            NotificationEvent.REGULATION_CHANGE_DETECTED.value,
            NotificationEvent.FORMULA_READY_FOR_REVIEW.value,
            NotificationEvent.FORMULA_ACTIVATED.value,
            NotificationEvent.FORMULA_REGENERATING.value,
            NotificationEvent.RUN_FAILED.value,
            NotificationEvent.DEFERRED_REMINDER.value,
        ],
        is_active=True,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


@pytest.mark.asyncio
class TestNotificationManager:
    """Test NotificationManager fire-and-forget behavior and retry logic."""

    async def test_notify_when_disabled(self, db):
        """Should skip notification when no active config exists."""
        manager = NotificationManager(db)

        # No exception should be raised
        await manager.notify(
            event=NotificationEvent.FORMULA_READY_FOR_REVIEW,
            evolution_run_id=1,
            run_id=1,
            function_name="test_func",
            change_summary="Test change",
            dashboard_url="/admin/runs/1",
        )

        # No logs should be created
        from sqlalchemy import select
        result = await db.execute(select(NotificationLog))
        logs = result.scalars().all()
        assert len(logs) == 0

    async def test_notify_skips_disabled_event(self, db, notification_config):
        """Should skip notification when event type is not enabled."""
        # Disable FORMULA_ACTIVATED event
        notification_config.enabled_events = [
            NotificationEvent.FORMULA_READY_FOR_REVIEW.value,
        ]
        await db.commit()

        manager = NotificationManager(db)

        await manager.notify(
            event=NotificationEvent.FORMULA_ACTIVATED,
            evolution_run_id=1,
            function_name="test_func",
            version="1.0",
            decision="ACCEPT",
            dashboard_url="/admin/runs/1",
        )

        # No logs should be created
        from sqlalchemy import select
        result = await db.execute(select(NotificationLog))
        logs = result.scalars().all()
        assert len(logs) == 0

    @patch("src.application.notification_manager.SmtpNotifier")
    @patch("src.infrastructure.encryption.decrypt_value")
    async def test_notify_successful_send(
        self, mock_decrypt, mock_notifier_class, db, notification_config
    ):
        """Should create success log entry after successful send."""
        # Mock decryption
        mock_decrypt.return_value = "decrypted_password"

        # Mock notifier
        mock_notifier = AsyncMock()
        mock_notifier.send = AsyncMock(return_value=True)
        mock_notifier_class.from_config.return_value = mock_notifier

        manager = NotificationManager(db)

        await manager.notify_formula_ready_for_review(
            run_id=1,
            function_name="test_func",
            change_summary="Threshold updated",
            dashboard_url="/admin/runs/1",
        )

        # Should have created success log
        from sqlalchemy import select
        result = await db.execute(select(NotificationLog))
        logs = result.scalars().all()
        assert len(logs) == 1
        assert logs[0].event == NotificationEvent.FORMULA_READY_FOR_REVIEW.value
        assert logs[0].success is True
        assert logs[0].error_message is None
        assert logs[0].retry_count == 0

    @patch("src.application.notification_manager.SmtpNotifier")
    @patch("src.infrastructure.encryption.decrypt_value")
    async def test_notify_retry_on_failure_high_priority(
        self, mock_decrypt, mock_notifier_class, db, notification_config
    ):
        """Should retry high-priority events up to 3 times."""
        mock_decrypt.return_value = "decrypted_password"

        # Mock notifier to always fail
        mock_notifier = AsyncMock()
        mock_notifier.send = AsyncMock(return_value=False)
        mock_notifier_class.from_config.return_value = mock_notifier

        manager = NotificationManager(db)

        await manager.notify_formula_ready_for_review(
            run_id=1,
            function_name="test_func",
            change_summary="Threshold updated",
            dashboard_url="/admin/runs/1",
        )

        # Should have been called 3 times (MAX_RETRIES)
        assert mock_notifier.send.call_count == 3

        # Should have created failure log with retry_count=2
        from sqlalchemy import select
        result = await db.execute(select(NotificationLog))
        logs = result.scalars().all()
        assert len(logs) == 1
        assert logs[0].success is False
        assert logs[0].retry_count == 2  # 0, 1, 2 = 3 attempts
        assert "Failed after 3 attempts" in logs[0].error_message

    @patch("src.application.notification_manager.SmtpNotifier")
    @patch("src.infrastructure.encryption.decrypt_value")
    async def test_notify_no_retry_for_low_priority(
        self, mock_decrypt, mock_notifier_class, db, notification_config
    ):
        """Should NOT retry low-priority events."""
        mock_decrypt.return_value = "decrypted_password"

        # Mock notifier to always fail
        mock_notifier = AsyncMock()
        mock_notifier.send = AsyncMock(return_value=False)
        mock_notifier_class.from_config.return_value = mock_notifier

        manager = NotificationManager(db)

        await manager.notify_formula_activated(
            run_id=1,
            function_name="test_func",
            version="1.0",
            decision="ACCEPT",
            dashboard_url="/admin/runs/1",
        )

        # Should have been called only once (no retry for low-priority)
        assert mock_notifier.send.call_count == 1

        # Should have created failure log with retry_count=0
        from sqlalchemy import select
        result = await db.execute(select(NotificationLog))
        logs = result.scalars().all()
        assert len(logs) == 1
        assert logs[0].success is False
        assert logs[0].retry_count == 0

    @patch("src.application.notification_manager.SmtpNotifier")
    @patch("src.infrastructure.encryption.decrypt_value")
    async def test_notify_fire_and_forget_never_raises(
        self, mock_decrypt, mock_notifier_class, db, notification_config
    ):
        """Should never raise exceptions (fire-and-forget)."""
        mock_decrypt.side_effect = Exception("Decryption failed!")

        manager = NotificationManager(db)

        # Should NOT raise exception
        await manager.notify_run_failed(
            run_id=1,
            failed_step="PARSING",
            error="Parser error",
            dashboard_url="/admin/runs/1",
        )

        # No logs should be created (exception occurred before log creation)
        from sqlalchemy import select
        result = await db.execute(select(NotificationLog))
        logs = result.scalars().all()
        assert len(logs) == 0

    @patch("src.application.notification_manager.SmtpNotifier")
    @patch("src.infrastructure.encryption.decrypt_value")
    async def test_all_convenience_methods(
        self, mock_decrypt, mock_notifier_class, db, notification_config
    ):
        """Should provide convenience methods for all 6 event types."""
        mock_decrypt.return_value = "decrypted_password"

        mock_notifier = AsyncMock()
        mock_notifier.send = AsyncMock(return_value=True)
        mock_notifier_class.from_config.return_value = mock_notifier

        manager = NotificationManager(db)

        # Test all 6 convenience methods
        await manager.notify_regulation_change_detected(
            page_name="Test Page",
            page_url="https://nta.jp/test",
            snapshot_id=1,
            dashboard_url="/admin/snapshots/1",
        )

        await manager.notify_formula_ready_for_review(
            run_id=1,
            function_name="test_func",
            change_summary="Test change",
            dashboard_url="/admin/runs/1",
        )

        await manager.notify_formula_activated(
            run_id=1,
            function_name="test_func",
            version="1.0",
            decision="ACCEPT",
            dashboard_url="/admin/runs/1",
        )

        await manager.notify_formula_regenerating(
            run_id=1,
            attempt=2,
            max_attempts=3,
            hints="Try again",
            dashboard_url="/admin/runs/1",
        )

        await manager.notify_run_failed(
            run_id=1,
            failed_step="PARSING",
            error="Parser error",
            dashboard_url="/admin/runs/1",
        )

        await manager.notify_deferred_reminder(
            deferred_count=5,
            deferred_runs=[{"id": 1, "summary": "Test", "date": "2024-01-01"}],
            dashboard_url="/admin/evolution/deferred",
        )

        # Should have created 6 success logs
        from sqlalchemy import select
        result = await db.execute(select(NotificationLog))
        logs = result.scalars().all()
        assert len(logs) == 6
        assert all(log.success for log in logs)
