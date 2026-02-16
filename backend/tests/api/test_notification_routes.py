"""Tests for notification API routes."""

import pytest
from httpx import AsyncClient

from src.infrastructure.models import NotificationConfig, NotificationLog
from src.domain.enums import NotificationEvent


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
        ],
        is_active=True,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


@pytest.mark.asyncio
class TestNotificationConfigAPI:
    """Test notification configuration endpoints."""

    async def test_create_notification_config(self, client: AsyncClient):
        """Should create a new notification configuration."""
        payload = {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_user": "test@gmail.com",
            "smtp_password": "secret_password",
            "sender_email": "noreply@taxpilot.com",
            "recipient_emails": ["admin@example.com"],
            "enabled_events": [
                "REGULATION_CHANGE_DETECTED",
                "FORMULA_READY_FOR_REVIEW",
            ],
        }

        response = await client.post("/admin/notifications/config", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["smtp_host"] == "smtp.gmail.com"
        assert data["smtp_port"] == 587
        assert data["smtp_user"] == "test@gmail.com"
        assert data["masked_password"] == "***************"  # masked
        assert data["sender_email"] == "noreply@taxpilot.com"
        assert data["recipient_emails"] == ["admin@example.com"]
        assert data["is_active"] is True

    async def test_update_notification_config(
        self, client: AsyncClient, notification_config
    ):
        """Should update existing notification configuration."""
        payload = {
            "smtp_host": "smtp.sendgrid.net",
            "smtp_port": 465,
            "smtp_user": "apikey",
            "smtp_password": "new_password",
            "sender_email": "alerts@taxpilot.com",
            "recipient_emails": ["newadmin@example.com"],
            "enabled_events": ["FORMULA_READY_FOR_REVIEW", "RUN_FAILED"],
        }

        response = await client.post("/admin/notifications/config", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["smtp_host"] == "smtp.sendgrid.net"
        assert data["smtp_port"] == 465
        assert data["recipient_emails"] == ["newadmin@example.com"]
        assert "RUN_FAILED" in data["enabled_events"]

    async def test_get_notification_config(
        self, client: AsyncClient, notification_config
    ):
        """Should retrieve active notification configuration."""
        response = await client.get("/admin/notifications/config")

        assert response.status_code == 200
        data = response.json()
        assert data["smtp_host"] == "smtp.example.com"
        assert data["smtp_port"] == 587
        assert data["masked_password"] == "***************"
        assert len(data["recipient_emails"]) == 2

    async def test_get_notification_config_not_found(self, client: AsyncClient):
        """Should return None when no config exists."""
        response = await client.get("/admin/notifications/config")

        assert response.status_code == 200
        assert response.json() is None

    async def test_disable_notification_config(
        self, client: AsyncClient, notification_config, db
    ):
        """Should deactivate the notification configuration."""
        response = await client.delete("/admin/notifications/config")

        assert response.status_code == 200
        assert response.json()["message"] == "Notification configuration disabled"

        # Verify config is deactivated
        await db.refresh(notification_config)
        assert notification_config.is_active is False

    async def test_disable_notification_config_not_found(self, client: AsyncClient):
        """Should return 404 when no active config to disable."""
        response = await client.delete("/admin/notifications/config")

        assert response.status_code == 404
        assert "No active config found" in response.json()["detail"]


@pytest.mark.asyncio
class TestNotificationLogsAPI:
    """Test notification logs endpoints."""

    async def test_list_notification_logs(
        self, client: AsyncClient, notification_config, db, evolution_run
    ):
        """Should list notification logs with default pagination."""
        # Create some logs
        log1 = NotificationLog(
            event=NotificationEvent.FORMULA_READY_FOR_REVIEW.value,
            recipient_emails=["admin@example.com"],
            subject="Test notification 1",
            success=True,
            retry_count=0,
            evolution_run_id=evolution_run.id,
        )
        log2 = NotificationLog(
            event=NotificationEvent.RUN_FAILED.value,
            recipient_emails=["admin@example.com"],
            subject="Test notification 2",
            success=False,
            error_message="SMTP connection failed",
            retry_count=2,
            evolution_run_id=evolution_run.id,
        )
        db.add_all([log1, log2])
        await db.commit()

        response = await client.get("/admin/notifications/logs")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["event"] in [
            NotificationEvent.FORMULA_READY_FOR_REVIEW.value,
            NotificationEvent.RUN_FAILED.value,
        ]

    async def test_list_notification_logs_filter_by_event(
        self, client: AsyncClient, db, evolution_run
    ):
        """Should filter logs by event type."""
        log1 = NotificationLog(
            event=NotificationEvent.FORMULA_READY_FOR_REVIEW.value,
            recipient_emails=["admin@example.com"],
            subject="Test 1",
            success=True,
            retry_count=0,
        )
        log2 = NotificationLog(
            event=NotificationEvent.RUN_FAILED.value,
            recipient_emails=["admin@example.com"],
            subject="Test 2",
            success=False,
            retry_count=0,
        )
        db.add_all([log1, log2])
        await db.commit()

        response = await client.get(
            "/admin/notifications/logs",
            params={"event": NotificationEvent.FORMULA_READY_FOR_REVIEW.value},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["event"] == NotificationEvent.FORMULA_READY_FOR_REVIEW.value

    async def test_list_notification_logs_filter_by_success(
        self, client: AsyncClient, db
    ):
        """Should filter logs by success status."""
        log1 = NotificationLog(
            event=NotificationEvent.FORMULA_READY_FOR_REVIEW.value,
            recipient_emails=["admin@example.com"],
            subject="Test 1",
            success=True,
            retry_count=0,
        )
        log2 = NotificationLog(
            event=NotificationEvent.RUN_FAILED.value,
            recipient_emails=["admin@example.com"],
            subject="Test 2",
            success=False,
            retry_count=0,
        )
        db.add_all([log1, log2])
        await db.commit()

        response = await client.get(
            "/admin/notifications/logs", params={"success": False}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["success"] is False

    async def test_list_notification_logs_pagination(self, client: AsyncClient, db):
        """Should paginate logs correctly."""
        # Create 10 logs
        logs = [
            NotificationLog(
                event=NotificationEvent.FORMULA_READY_FOR_REVIEW.value,
                recipient_emails=["admin@example.com"],
                subject=f"Test {i}",
                success=True,
                retry_count=0,
            )
            for i in range(10)
        ]
        db.add_all(logs)
        await db.commit()

        response = await client.get(
            "/admin/notifications/logs", params={"limit": 5, "offset": 0}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

        response2 = await client.get(
            "/admin/notifications/logs", params={"limit": 5, "offset": 5}
        )

        data2 = response2.json()
        assert len(data2) == 5


@pytest.mark.asyncio
class TestNotificationStatsAPI:
    """Test notification statistics endpoint."""

    async def test_get_notification_stats(self, client: AsyncClient, db):
        """Should return notification delivery statistics."""
        # Create diverse logs
        logs = [
            NotificationLog(
                event=NotificationEvent.FORMULA_READY_FOR_REVIEW.value,
                recipient_emails=["admin@example.com"],
                subject="Test 1",
                success=True,
                retry_count=0,
            ),
            NotificationLog(
                event=NotificationEvent.FORMULA_READY_FOR_REVIEW.value,
                recipient_emails=["admin@example.com"],
                subject="Test 2",
                success=True,
                retry_count=0,
            ),
            NotificationLog(
                event=NotificationEvent.RUN_FAILED.value,
                recipient_emails=["admin@example.com"],
                subject="Test 3",
                success=False,
                retry_count=2,
            ),
            NotificationLog(
                event=NotificationEvent.FORMULA_ACTIVATED.value,
                recipient_emails=["admin@example.com"],
                subject="Test 4",
                success=True,
                retry_count=0,
            ),
        ]
        db.add_all(logs)
        await db.commit()

        response = await client.get("/admin/notifications/logs/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_sent"] == 4
        assert data["successful"] == 3
        assert data["failed"] == 1
        assert data["success_rate"] == 75.0
        assert NotificationEvent.FORMULA_READY_FOR_REVIEW.value in data["by_event_type"]
        assert data["by_event_type"][NotificationEvent.FORMULA_READY_FOR_REVIEW.value] == 2

    async def test_get_notification_stats_empty(self, client: AsyncClient):
        """Should return zero stats when no logs exist."""
        response = await client.get("/admin/notifications/logs/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_sent"] == 0
        assert data["successful"] == 0
        assert data["failed"] == 0
        assert data["success_rate"] == 0.0
        assert data["by_event_type"] == {}
