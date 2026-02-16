# Phase 6F: Email Notifications

**Goal:** Build an email notification system that alerts the admin when pipeline events occur (new regulation detected, formula ready for review, etc.). Design with a pluggable interface so future notification channels (Slack, SendGrid, webhooks) can be added without changing the pipeline code.

**Depends on:** Phase 6E (pipeline events to trigger notifications)
**Produces:** `NotificationService` protocol, `SmtpNotifier` implementation, email templates, notification configuration in Streamlit, notification logging

---

## Context

The Evolution Loop pipeline produces several events that require admin attention:
- A new regulation change is detected on the NTA website
- A formula has been generated and is ready for review
- An admin accepts or modifies a formula
- A pipeline run fails
- Deferred tasks are piling up

Without notifications, the admin would need to manually check the dashboard for updates. Email notifications ensure timely awareness and response.

**Design approach:** The notification system uses a **pluggable interface**. The core pipeline dispatches events to a `NotificationManager`, which checks configuration and delegates to the active notifier. For MVP, only SMTP email is implemented. The protocol is provider-agnostic, so Slack, SendGrid, or webhook adapters can be added later without changing any pipeline code.

---

## Tasks

### Task 6F.1: Enums

**File:** `backend/src/domain/enums.py`

```python
class NotificationEvent(str, Enum):
    """Pipeline events that can trigger notifications."""
    REGULATION_CHANGE_DETECTED = "REGULATION_CHANGE_DETECTED"
    FORMULA_READY_FOR_REVIEW = "FORMULA_READY_FOR_REVIEW"
    FORMULA_ACTIVATED = "FORMULA_ACTIVATED"
    FORMULA_REGENERATING = "FORMULA_REGENERATING"
    RUN_FAILED = "RUN_FAILED"
    DEFERRED_REMINDER = "DEFERRED_REMINDER"
```

### Task 6F.2: Notification Event Catalog

| Event | When It Fires | Email Subject Example | Priority |
|-------|--------------|----------------------|----------|
| `REGULATION_CHANGE_DETECTED` | NTA crawler detects a page change | `[TaxPilot] New regulation change detected: income_tax_rates` | High |
| `FORMULA_READY_FOR_REVIEW` | Pipeline finishes generating code/schema, enters `AWAITING_REVIEW` | `[TaxPilot] New formula ready for review (Run #42)` | High |
| `FORMULA_ACTIVATED` | Admin accepts or modifies and activates a formula | `[TaxPilot] Formula activated: calc_income_tax v2025.1` | Medium |
| `FORMULA_REGENERATING` | Admin requests LLM regeneration | `[TaxPilot] Regeneration requested for Run #42 (attempt 2/3)` | Low |
| `RUN_FAILED` | Pipeline fails at any step | `[TaxPilot] Evolution run #42 failed at PARSING step` | High |
| `DEFERRED_REMINDER` | Weekly digest of deferred runs still pending manual action | `[TaxPilot] 3 deferred regulation updates await manual handling` | Medium |

### Task 6F.3: Database Models

**File:** `backend/src/infrastructure/models.py`

```python
class NotificationConfig(Base):
    """Persists notification settings (SMTP config and preferences)."""
    __tablename__ = "notification_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    smtp_host: Mapped[str] = mapped_column(String(200), nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587)
    smtp_user: Mapped[str] = mapped_column(String(200), nullable=False)
    encrypted_smtp_password: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # Encrypted via Fernet (same as LLM tokens)
    sender_email: Mapped[str] = mapped_column(String(200), nullable=False)
    recipient_emails: Mapped[list] = mapped_column(
        JSONB, nullable=False
    )  # ["admin1@example.com", "admin2@example.com"]
    enabled_events: Mapped[list] = mapped_column(
        JSONB, nullable=False
    )  # ["REGULATION_CHANGE_DETECTED", "FORMULA_READY_FOR_REVIEW", ...]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class NotificationLog(Base):
    """Records every notification attempt."""
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    event: Mapped[str] = mapped_column(String(50), nullable=False)
    recipient: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # SENT / FAILED / SKIPPED
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    evolution_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("evolution_runs.id"), nullable=True
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_notification_logs_event_sent", "event", "sent_at"),
        Index("ix_notification_logs_evolution_run_id", "evolution_run_id"),
    )
```

### Task 6F.4: Pydantic Schemas

**File:** `backend/src/domain/schemas.py`

```python
class NotificationConfigSchema(BaseModel):
    """Schema for notification configuration."""
    smtp_host: str = Field(description="SMTP server hostname")
    smtp_port: int = Field(default=587, description="SMTP port (587 for TLS)")
    smtp_user: str = Field(description="SMTP username")
    smtp_password: str = Field(
        description="SMTP password (will be encrypted at rest)"
    )
    sender_email: str = Field(description="From email address")
    recipient_emails: list[str] = Field(
        description="List of recipient email addresses"
    )
    enabled_events: list[str] = Field(
        description="List of NotificationEvent values to enable"
    )


class NotificationConfigResponse(BaseModel):
    """Response schema for notification config (password masked)."""
    id: int
    smtp_host: str
    smtp_port: int
    smtp_user: str
    masked_password: str = Field(description="Masked SMTP password")
    sender_email: str
    recipient_emails: list[str]
    enabled_events: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NotificationLogEntry(BaseModel):
    """A single notification log entry."""
    id: int
    event: str
    recipient: str
    subject: str
    status: str
    error_message: str | None
    evolution_run_id: int | None
    sent_at: datetime

    model_config = {"from_attributes": True}
```

### Task 6F.5: Notification Service Protocol

**File:** `backend/src/infrastructure/notification_service.py`

The pluggable interface and SMTP implementation:

```python
from abc import ABC, abstractmethod
from typing import Protocol

import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.encryption import decrypt_token
from src.infrastructure.models import NotificationConfig, NotificationLog
from src.logging_config import get_logger

logger = get_logger(__name__)


class NotificationService(Protocol):
    """Protocol for notification services.

    Implement this protocol to add new notification channels
    (Slack, SendGrid, webhooks, etc.) without changing pipeline code.
    """

    async def send(
        self,
        recipient: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
    ) -> bool:
        """Send a notification.

        Args:
            recipient: Recipient address (email, Slack channel, webhook URL).
            subject: Notification subject/title.
            html_body: HTML content of the notification.
            text_body: Plain text fallback (optional).

        Returns:
            True if sent successfully, False otherwise.
        """
        ...


class SmtpNotifier:
    """SMTP email notification implementation.

    Uses aiosmtplib for async email sending compatible with FastAPI.
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender

    async def send(
        self,
        recipient: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
    ) -> bool:
        """Send an email via SMTP."""
        msg = MIMEMultipart("alternative")
        msg["From"] = self.sender
        msg["To"] = recipient
        msg["Subject"] = subject

        if text_body:
            msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                use_tls=False,
                start_tls=True,
            )
            logger.info(f"Email sent to {recipient}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {recipient}: {e}")
            return False

    @classmethod
    async def from_config(cls, db: AsyncSession) -> "SmtpNotifier | None":
        """Create an SmtpNotifier from database configuration.

        Returns None if no active notification config exists.
        """
        from sqlalchemy import select

        result = await db.execute(
            select(NotificationConfig).where(NotificationConfig.is_active == True)
        )
        config = result.scalar_one_or_none()
        if config is None:
            return None

        password = decrypt_token(config.encrypted_smtp_password)
        return cls(
            host=config.smtp_host,
            port=config.smtp_port,
            username=config.smtp_user,
            password=password,
            sender=config.sender_email,
        )
```

### Task 6F.6: Email Templates

**File:** `backend/src/infrastructure/email_templates.py`

HTML email templates for each event type:

```python
"""HTML email templates for TaxPilot notifications.

Each template function returns (subject, html_body, text_body).
Templates use simple string formatting (no Jinja2 dependency for MVP).
"""

STYLE = """
<style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
    .container { max-width: 600px; margin: 0 auto; padding: 20px; }
    .header { background: #1a56db; color: white; padding: 16px; border-radius: 8px 8px 0 0; }
    .body { background: #f9fafb; padding: 20px; border: 1px solid #e5e7eb; }
    .footer { padding: 12px; text-align: center; color: #6b7280; font-size: 12px; }
    .badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600; }
    .badge-high { background: #fee2e2; color: #dc2626; }
    .badge-medium { background: #fef3c7; color: #d97706; }
    .badge-low { background: #dbeafe; color: #2563eb; }
    .btn { display: inline-block; padding: 10px 20px; background: #1a56db; color: white; text-decoration: none; border-radius: 6px; }
</style>
"""


def regulation_change_detected(
    page_name: str, page_url: str, snapshot_id: int, dashboard_url: str
) -> tuple[str, str, str]:
    """Template for REGULATION_CHANGE_DETECTED event."""
    subject = f"[TaxPilot] New regulation change detected: {page_name}"
    html = f"""
    {STYLE}
    <div class="container">
        <div class="header">
            <h2>Regulation Change Detected</h2>
        </div>
        <div class="body">
            <p>The NTA crawler has detected a content change on a monitored page:</p>
            <ul>
                <li><strong>Page:</strong> {page_name}</li>
                <li><strong>URL:</strong> <a href="{page_url}">{page_url}</a></li>
                <li><strong>Snapshot ID:</strong> {snapshot_id}</li>
            </ul>
            <p>The Evolution Loop will automatically parse this change and generate
            updated formulas for your review.</p>
            <p><a href="{dashboard_url}" class="btn">Open Dashboard</a></p>
        </div>
        <div class="footer">
            TaxPilot — Automated Tax Regulation Monitoring
        </div>
    </div>
    """
    text = (
        f"Regulation Change Detected\n\n"
        f"Page: {page_name}\n"
        f"URL: {page_url}\n"
        f"Snapshot ID: {snapshot_id}\n\n"
        f"Open dashboard: {dashboard_url}"
    )
    return subject, html, text


def formula_ready_for_review(
    run_id: int, function_name: str, change_summary: str, dashboard_url: str
) -> tuple[str, str, str]:
    """Template for FORMULA_READY_FOR_REVIEW event."""
    subject = f"[TaxPilot] New formula ready for review (Run #{run_id})"
    html = f"""
    {STYLE}
    <div class="container">
        <div class="header">
            <h2>Formula Ready for Review</h2>
        </div>
        <div class="body">
            <p><span class="badge badge-high">Action Required</span></p>
            <p>A new formula has been generated and requires your review:</p>
            <ul>
                <li><strong>Run:</strong> #{run_id}</li>
                <li><strong>Function:</strong> {function_name}</li>
                <li><strong>Change:</strong> {change_summary}</li>
            </ul>
            <p>You can Accept, Modify, Regenerate, or Skip this formula.</p>
            <p><a href="{dashboard_url}" class="btn">Review Now</a></p>
        </div>
        <div class="footer">
            TaxPilot — Automated Tax Regulation Monitoring
        </div>
    </div>
    """
    text = (
        f"Formula Ready for Review\n\n"
        f"Run: #{run_id}\n"
        f"Function: {function_name}\n"
        f"Change: {change_summary}\n\n"
        f"Review at: {dashboard_url}"
    )
    return subject, html, text


def formula_activated(
    function_name: str, version: str, decision: str, dashboard_url: str
) -> tuple[str, str, str]:
    """Template for FORMULA_ACTIVATED event."""
    subject = f"[TaxPilot] Formula activated: {function_name} v{version}"
    html = f"""
    {STYLE}
    <div class="container">
        <div class="header">
            <h2>Formula Activated</h2>
        </div>
        <div class="body">
            <p><span class="badge badge-medium">Info</span></p>
            <p>A formula has been activated:</p>
            <ul>
                <li><strong>Function:</strong> {function_name}</li>
                <li><strong>Version:</strong> {version}</li>
                <li><strong>Decision:</strong> {decision}</li>
            </ul>
            <p>The previous version has been archived. Rollback is available via the dashboard.</p>
            <p><a href="{dashboard_url}" class="btn">View Details</a></p>
        </div>
        <div class="footer">
            TaxPilot — Automated Tax Regulation Monitoring
        </div>
    </div>
    """
    text = (
        f"Formula Activated\n\n"
        f"Function: {function_name}\n"
        f"Version: {version}\n"
        f"Decision: {decision}\n\n"
        f"View at: {dashboard_url}"
    )
    return subject, html, text


def formula_regenerating(
    run_id: int, attempt: int, max_attempts: int, hints: str | None, dashboard_url: str
) -> tuple[str, str, str]:
    """Template for FORMULA_REGENERATING event."""
    subject = f"[TaxPilot] Regeneration requested for Run #{run_id} (attempt {attempt}/{max_attempts})"
    hints_text = hints or "No specific hints provided"
    html = f"""
    {STYLE}
    <div class="container">
        <div class="header">
            <h2>Formula Regeneration Requested</h2>
        </div>
        <div class="body">
            <p><span class="badge badge-low">Info</span></p>
            <ul>
                <li><strong>Run:</strong> #{run_id}</li>
                <li><strong>Attempt:</strong> {attempt} of {max_attempts}</li>
                <li><strong>Hints:</strong> {hints_text}</li>
            </ul>
            <p>The LLM will generate a new version. You will be notified when it is ready for review.</p>
        </div>
        <div class="footer">
            TaxPilot — Automated Tax Regulation Monitoring
        </div>
    </div>
    """
    text = (
        f"Regeneration Requested\n\n"
        f"Run: #{run_id}\n"
        f"Attempt: {attempt}/{max_attempts}\n"
        f"Hints: {hints_text}"
    )
    return subject, html, text


def run_failed(
    run_id: int, failed_step: str, error: str, dashboard_url: str
) -> tuple[str, str, str]:
    """Template for RUN_FAILED event."""
    subject = f"[TaxPilot] Evolution run #{run_id} failed at {failed_step} step"
    html = f"""
    {STYLE}
    <div class="container">
        <div class="header" style="background: #dc2626;">
            <h2>Evolution Run Failed</h2>
        </div>
        <div class="body">
            <p><span class="badge badge-high">Error</span></p>
            <ul>
                <li><strong>Run:</strong> #{run_id}</li>
                <li><strong>Failed Step:</strong> {failed_step}</li>
                <li><strong>Error:</strong> {error}</li>
            </ul>
            <p>Please check the dashboard for details and consider re-running.</p>
            <p><a href="{dashboard_url}" class="btn">View Run Details</a></p>
        </div>
        <div class="footer">
            TaxPilot — Automated Tax Regulation Monitoring
        </div>
    </div>
    """
    text = (
        f"Evolution Run Failed\n\n"
        f"Run: #{run_id}\n"
        f"Failed Step: {failed_step}\n"
        f"Error: {error}\n\n"
        f"View at: {dashboard_url}"
    )
    return subject, html, text


def deferred_reminder(
    deferred_count: int, deferred_runs: list[dict], dashboard_url: str
) -> tuple[str, str, str]:
    """Template for DEFERRED_REMINDER weekly digest."""
    subject = f"[TaxPilot] {deferred_count} deferred regulation updates await manual handling"
    runs_html = "".join(
        f"<li>Run #{r['id']}: {r['summary']} (deferred {r['date']})</li>"
        for r in deferred_runs
    )
    html = f"""
    {STYLE}
    <div class="container">
        <div class="header">
            <h2>Deferred Tasks Reminder</h2>
        </div>
        <div class="body">
            <p><span class="badge badge-medium">Reminder</span></p>
            <p>You have <strong>{deferred_count}</strong> deferred regulation updates
            that are waiting for manual handling:</p>
            <ul>{runs_html}</ul>
            <p><a href="{dashboard_url}" class="btn">Review Deferred Tasks</a></p>
        </div>
        <div class="footer">
            TaxPilot — Automated Tax Regulation Monitoring (Weekly Digest)
        </div>
    </div>
    """
    text = (
        f"Deferred Tasks Reminder\n\n"
        f"You have {deferred_count} deferred regulation updates.\n\n"
        f"View at: {dashboard_url}"
    )
    return subject, html, text
```

### Task 6F.7: Notification Manager (Application Layer)

**File:** `backend/src/application/notification_manager.py`

Receives pipeline events, checks if notification is enabled, dispatches via the active notifier, and logs the result:

```python
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure import email_templates
from src.infrastructure.models import NotificationConfig, NotificationLog
from src.infrastructure.notification_service import SmtpNotifier
from src.logging_config import get_logger

logger = get_logger(__name__)

# Dashboard URL (configured via env or settings)
DASHBOARD_URL = "http://localhost:8501"

# Events that warrant retry on failure (critical for admin awareness)
_HIGH_PRIORITY_EVENTS = {
    "REGULATION_CHANGE_DETECTED",
    "PIPELINE_FAILED",
    "FORMULA_READY_FOR_REVIEW",
}


class NotificationManager:
    """Dispatches notifications for pipeline events.

    Checks if the event is enabled in NotificationConfig,
    then sends to all configured recipients via the active notifier.
    Fire-and-forget — notification failures do NOT block the pipeline.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def notify(
        self,
        event: str,
        context: dict,
        evolution_run_id: int | None = None,
    ) -> None:
        """Send a notification for a pipeline event.

        Args:
            event: NotificationEvent value.
            context: Event-specific context dict for template rendering.
            evolution_run_id: Optional link to evolution run.
        """
        try:
            # Get active notification config
            result = await self.db.execute(
                select(NotificationConfig).where(
                    NotificationConfig.is_active == True
                )
            )
            config = result.scalar_one_or_none()
            if config is None:
                logger.debug(f"No notification config — skipping {event}")
                return

            # Check if this event is enabled
            if event not in config.enabled_events:
                logger.debug(f"Event {event} not enabled — skipping")
                return

            # Build the email
            subject, html, text = self._render_template(event, context)

            # Create notifier
            notifier = await SmtpNotifier.from_config(self.db)
            if notifier is None:
                logger.warning("Could not create SmtpNotifier — skipping")
                return

            # Send to all recipients with retry for high-priority events
            max_retries = 3 if event in _HIGH_PRIORITY_EVENTS else 1
            for recipient in config.recipient_emails:
                success = False
                last_error: str | None = None
                for attempt in range(max_retries):
                    success = await notifier.send(recipient, subject, html, text)
                    if success:
                        break
                    last_error = f"Attempt {attempt + 1}/{max_retries} failed"
                    if attempt < max_retries - 1:
                        # Exponential backoff: 1s, 2s, 4s
                        await asyncio.sleep(2 ** attempt)
                        logger.warning(
                            f"Retrying notification to {recipient} "
                            f"(attempt {attempt + 2}/{max_retries})"
                        )

                # Log the final outcome
                log = NotificationLog(
                    event=event,
                    recipient=recipient,
                    subject=subject,
                    status="SENT" if success else "FAILED",
                    error_message=None if success else last_error,
                    evolution_run_id=evolution_run_id,
                )
                self.db.add(log)

            await self.db.flush()

        except Exception as e:
            # Fire-and-forget: log but do NOT raise
            logger.error(f"Notification dispatch failed for {event}: {e}")

    def _render_template(
        self, event: str, context: dict
    ) -> tuple[str, str, str]:
        """Render the email template for the given event.

        Returns: (subject, html_body, text_body)
        """
        dashboard = context.get("dashboard_url", DASHBOARD_URL)

        if event == "REGULATION_CHANGE_DETECTED":
            return email_templates.regulation_change_detected(
                page_name=context["page_name"],
                page_url=context["page_url"],
                snapshot_id=context["snapshot_id"],
                dashboard_url=dashboard,
            )
        elif event == "FORMULA_READY_FOR_REVIEW":
            return email_templates.formula_ready_for_review(
                run_id=context["run_id"],
                function_name=context["function_name"],
                change_summary=context["change_summary"],
                dashboard_url=dashboard,
            )
        elif event == "FORMULA_ACTIVATED":
            return email_templates.formula_activated(
                function_name=context["function_name"],
                version=context["version"],
                decision=context["decision"],
                dashboard_url=dashboard,
            )
        elif event == "FORMULA_REGENERATING":
            return email_templates.formula_regenerating(
                run_id=context["run_id"],
                attempt=context["attempt"],
                max_attempts=context["max_attempts"],
                hints=context.get("hints"),
                dashboard_url=dashboard,
            )
        elif event == "RUN_FAILED":
            return email_templates.run_failed(
                run_id=context["run_id"],
                failed_step=context["failed_step"],
                error=context["error"],
                dashboard_url=dashboard,
            )
        elif event == "DEFERRED_REMINDER":
            return email_templates.deferred_reminder(
                deferred_count=context["deferred_count"],
                deferred_runs=context["deferred_runs"],
                dashboard_url=dashboard,
            )
        else:
            raise ValueError(f"Unknown notification event: {event}")
```

### Task 6F.8: Integration with Pipeline (Phase 6E)

**File:** `backend/src/application/evolution_service.py` (update)

Add notification dispatch calls at each pipeline event point:

```python
# After change detection (in start_run):
await self.notifier.notify(
    "REGULATION_CHANGE_DETECTED",
    {"page_name": page_name, "page_url": page_url, "snapshot_id": snapshot_id},
)

# After reaching AWAITING_REVIEW (in start_run):
await self.notifier.notify(
    "FORMULA_READY_FOR_REVIEW",
    {"run_id": run.id, "function_name": func_name, "change_summary": summary},
    evolution_run_id=run.id,
)

# After activation (in _handle_accept / _handle_modify):
await self.notifier.notify(
    "FORMULA_ACTIVATED",
    {"function_name": name, "version": ver, "decision": decision},
    evolution_run_id=run.id,
)

# After regeneration request (in _handle_regenerate):
await self.notifier.notify(
    "FORMULA_REGENERATING",
    {"run_id": run.id, "attempt": count, "max_attempts": max, "hints": hints},
    evolution_run_id=run.id,
)

# On failure (in exception handler):
await self.notifier.notify(
    "RUN_FAILED",
    {"run_id": run.id, "failed_step": step, "error": str(e)},
    evolution_run_id=run.id,
)
```

**Integration flow:**

```
Pipeline step completes
       |
       v
NotificationManager.notify(event, context)
       |
       v
Check: is this event enabled in NotificationConfig?
       |
  yes  |  no
       v    → (skip)
SmtpNotifier.send(template, recipient)
       |
       v
Log to NotificationLog table
```

### Task 6F.9: Deferred Reminder Scheduler

**File:** `backend/src/infrastructure/scheduler.py` (update existing)

Add a weekly job for deferred task reminders:

```python
async def send_deferred_reminders():
    """Weekly job to remind admin about deferred evolution runs."""
    async with get_async_session() as db:
        # Query DEFERRED runs
        result = await db.execute(
            select(EvolutionRun).where(EvolutionRun.status == "DEFERRED")
        )
        deferred = result.scalars().all()

        if not deferred:
            return

        manager = NotificationManager(db)
        await manager.notify(
            "DEFERRED_REMINDER",
            {
                "deferred_count": len(deferred),
                "deferred_runs": [
                    {"id": r.id, "summary": r.error_message or "N/A", "date": str(r.completed_at)}
                    for r in deferred
                ],
            },
        )
        await db.commit()


def start_scheduler(crawl_interval_hours: int = 24):
    """Start all periodic schedulers."""
    # ... existing NTA crawler job ...

    # Weekly deferred reminder (every Monday at 9:00 AM)
    scheduler.add_job(
        send_deferred_reminders,
        "cron",
        day_of_week="mon",
        hour=9,
        minute=0,
        id="deferred_reminder",
        replace_existing=True,
    )

    scheduler.start()
```

### Task 6F.10: API Routes

**File:** `backend/src/api/notification_routes.py`

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.schemas import (
    NotificationConfigResponse,
    NotificationConfigSchema,
    NotificationLogEntry,
)
from src.infrastructure.database import get_db

router = APIRouter(prefix="/admin/notifications", tags=["Admin - Notifications"])


@router.put(
    "/config",
    response_model=NotificationConfigResponse,
    summary="Create or update notification configuration",
)
async def put_notification_config(
    data: NotificationConfigSchema, db: AsyncSession = Depends(get_db)
):
    # Encrypt SMTP password, upsert config
    pass


@router.get(
    "/config",
    response_model=NotificationConfigResponse | None,
    summary="Get current notification configuration (password masked)",
)
async def get_notification_config(db: AsyncSession = Depends(get_db)):
    pass


@router.post(
    "/test",
    summary="Send a test notification email",
)
async def test_notification(db: AsyncSession = Depends(get_db)):
    # Send a simple test email to verify SMTP config works
    pass


@router.get(
    "/logs",
    response_model=list[NotificationLogEntry],
    summary="Get notification history",
)
async def get_notification_logs(
    limit: int = 50, db: AsyncSession = Depends(get_db)
):
    pass
```

**Update `backend/src/main.py`:**

```python
from src.api.notification_routes import router as notification_router

# Inside create_app():
application.include_router(notification_router)
```

### Task 6F.11: Streamlit Admin Page — Notifications

**File:** `admin/app.py` (new page)

The "Notifications" page provides:

**1. SMTP Configuration Form:**
- SMTP host, port, username, password (password field)
- Sender email address
- Recipient emails (comma-separated or multi-input)
- Save button → calls `PUT /admin/notifications/config`

**2. Event Toggles:**
- Checkbox for each notification event type
- Description of when each event fires
- Example subject line shown for each

**3. Test Email:**
- "Send Test Email" button → calls `POST /admin/notifications/test`
- Shows success/failure result with details

**4. Notification History:**
- Table of recent notifications: event, recipient, subject, status, timestamp
- Filter by event type and status (SENT/FAILED)
- Shows error details for FAILED notifications

### Task 6F.12: Configuration

**File:** `backend/src/config.py`

Add new fields to the existing `Settings(BaseSettings)` class (per project convention — all config via `pydantic-settings`):

```python
class Settings(BaseSettings):
    # ... existing fields ...

    # Notifications (Phase 6F)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_sender: str = "taxpilot@example.com"
    notification_recipients: str = ""  # Comma-separated list

    model_config = SettingsConfigDict(env_file=".env")
```

Access via `settings.smtp_host` etc. — never use bare `os.getenv()` (per `security.mdc`).

### Task 6F.13: Environment Variables

**File:** `.env.example`

Add:

```bash
# Notifications (Phase 6F)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_SENDER=taxpilot@example.com
NOTIFICATION_RECIPIENTS=admin@example.com
```

### Task 6F.14: Dependencies

**File:** `backend/pyproject.toml`

```toml
[project]
dependencies = [
    # ... existing deps ...
    "aiosmtplib>=3.0.0",
]
```

### Task 6F.15: Alembic Migration

```bash
alembic revision --autogenerate -m "add notification_configs and notification_logs tables"
```

---

## Security

- SMTP password **encrypted at rest** (same Fernet approach as LLM tokens in Phase 6A)
- SMTP password **never logged**, never returned in full via API (masked)
- Email content contains only **regulation change summaries and dashboard links** — no user PII
- Notification config changes logged to `AuditLog`
- Failed sends are logged but **do not block the pipeline** (fire-and-forget with error logging)
- Recipient emails validated for format before storage

---

## Test Specification

Per `testing-policy.md`, every task must ship with tests.

### Unit Tests (`tests/infrastructure/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_smtp_notifier.py` | `SmtpNotifier` | send() dispatches email via mock aiosmtplib, handles SMTP connection failure gracefully, handles authentication failure, uses TLS when configured |
| `test_email_templates.py` | `email_templates.py` | Each template function returns (subject, html, text) tuple, subject includes event-specific info, HTML contains required elements (CTA button, run ID, etc.), plain text fallback is readable |

### Unit Tests (`tests/application/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_notification_manager.py` | `NotificationManager` | dispatch() sends to enabled events only, dispatch() skips disabled events, dispatch() retries failed sends (up to 3 attempts with exponential backoff), dispatch() logs all outcomes to `NotificationLog`, handles no configured recipients gracefully |

### Integration Tests (`tests/api/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_notification_routes.py` | API endpoints | `PUT /admin/notifications/config` stores SMTP settings (encrypted password), `POST /admin/notifications/test` sends test email (mock SMTP), `GET /admin/notifications/log` returns log entries with pagination |

### Test Conventions
- Mock `aiosmtplib.SMTP` — never send real emails in tests.
- Use factory fixtures for `NotificationConfig` and `NotificationLog` records.
- Test email template rendering with sample data.

---

## Acceptance Criteria

1. Admin can configure SMTP settings via Streamlit UI or env vars.
2. Test email button sends successfully and records in `NotificationLog`.
3. When NTA change is detected, email is sent to configured recipients.
4. When formula is ready for review, email includes run ID and change summary.
5. When formula is activated, email confirms the function name and version.
6. When a run fails, email includes the failed step and error message.
7. Admin can toggle which events trigger notifications.
8. Failed email sends are logged but do **not** crash the pipeline.
9. DEFERRED reminder email is sent weekly (configurable schedule).
10. All notification events are in the `NotificationLog` table with status (SENT/FAILED/SKIPPED).
