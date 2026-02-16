"""API routes for notification configuration and logs — admin only."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.schemas import NotificationConfigResponse, NotificationConfigSchema, NotificationLogEntry
from src.infrastructure.database import get_db
from src.infrastructure.encryption import encrypt_value
from src.infrastructure.models import NotificationConfig, NotificationLog

router = APIRouter(prefix="/admin/notifications", tags=["Admin - Notifications"])


@router.post(
    "/config",
    response_model=NotificationConfigResponse,
    summary="Create or update notification configuration",
    description="Configure SMTP settings and enabled event types. Only one active config is allowed.",
)
async def upsert_notification_config(
    config: NotificationConfigSchema,
    db: AsyncSession = Depends(get_db),
):
    """Create or update notification configuration.

    Args:
        config: SMTP settings, recipients, and enabled events

    Returns:
        Created/updated config with masked password
    """
    # Encrypt SMTP password
    encrypted_password = encrypt_value(config.smtp_password)

    # Convert enum values to strings for JSONB storage
    enabled_events_str = [event.value for event in config.enabled_events]

    # Check if an active config already exists
    result = await db.execute(
        select(NotificationConfig).where(NotificationConfig.is_active == True)
    )
    existing = result.scalars().first()

    if existing:
        # Update existing config
        existing.smtp_host = config.smtp_host
        existing.smtp_port = config.smtp_port
        existing.smtp_user = config.smtp_user
        existing.encrypted_smtp_password = encrypted_password
        existing.sender_email = config.sender_email
        existing.recipient_emails = config.recipient_emails
        existing.enabled_events = enabled_events_str

        record = existing
    else:
        # Create new config
        record = NotificationConfig(
            smtp_host=config.smtp_host,
            smtp_port=config.smtp_port,
            smtp_user=config.smtp_user,
            encrypted_smtp_password=encrypted_password,
            sender_email=config.sender_email,
            recipient_emails=config.recipient_emails,
            enabled_events=enabled_events_str,
            is_active=True,
        )
        db.add(record)

    await db.commit()
    await db.refresh(record)

    return NotificationConfigResponse(
        id=record.id,
        smtp_host=record.smtp_host,
        smtp_port=record.smtp_port,
        smtp_user=record.smtp_user,
        masked_password="***" * 5,
        sender_email=record.sender_email,
        recipient_emails=record.recipient_emails,
        enabled_events=record.enabled_events,
        is_active=record.is_active,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get(
    "/config",
    response_model=NotificationConfigResponse | None,
    summary="Get active notification configuration",
    description="Returns the active notification config with masked SMTP password.",
)
async def get_notification_config(db: AsyncSession = Depends(get_db)):
    """Get active notification configuration.

    Returns:
        Active config or None if no config exists
    """
    result = await db.execute(
        select(NotificationConfig).where(NotificationConfig.is_active == True)
    )
    config = result.scalars().first()

    if not config:
        return None

    return NotificationConfigResponse(
        id=config.id,
        smtp_host=config.smtp_host,
        smtp_port=config.smtp_port,
        smtp_user=config.smtp_user,
        masked_password="***" * 5,
        sender_email=config.sender_email,
        recipient_emails=config.recipient_emails,
        enabled_events=config.enabled_events,
        is_active=config.is_active,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.delete(
    "/config",
    summary="Disable notification configuration",
    description="Deactivates the current notification config (does not delete).",
)
async def disable_notification_config(db: AsyncSession = Depends(get_db)):
    """Disable active notification configuration.

    Returns:
        Confirmation message
    """
    result = await db.execute(
        select(NotificationConfig).where(NotificationConfig.is_active == True)
    )
    config = result.scalars().first()

    if not config:
        raise HTTPException(status_code=404, detail="No active config found")

    config.is_active = False
    await db.commit()

    return {"message": "Notification configuration disabled"}


@router.get(
    "/logs",
    response_model=list[NotificationLogEntry],
    summary="List notification logs with optional filtering",
    description="Returns notification history with optional event type and success filtering.",
)
async def list_notification_logs(
    event: str | None = Query(None, description="Filter by event type"),
    success: bool | None = Query(None, description="Filter by success status"),
    limit: int = Query(50, le=100, description="Maximum number of logs to return"),
    offset: int = Query(0, ge=0, description="Number of logs to skip"),
    db: AsyncSession = Depends(get_db),
):
    """List notification logs with optional filtering.

    Args:
        event: Filter by event type (e.g., FORMULA_READY_FOR_REVIEW)
        success: Filter by success status (true/false)
        limit: Maximum number of logs to return
        offset: Number of logs to skip

    Returns:
        List of NotificationLogEntry objects
    """
    query = select(NotificationLog).order_by(NotificationLog.sent_at.desc())

    if event:
        query = query.where(NotificationLog.event == event)

    if success is not None:
        query = query.where(NotificationLog.success == success)

    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    logs = result.scalars().all()

    return [
        NotificationLogEntry(
            id=log.id,
            event=log.event,
            evolution_run_id=log.evolution_run_id,
            recipient_emails=log.recipient_emails,
            subject=log.subject,
            sent_at=log.sent_at,
            success=log.success,
            error_message=log.error_message,
            retry_count=log.retry_count,
        )
        for log in logs
    ]


@router.get(
    "/logs/stats",
    summary="Get notification statistics",
    description="Returns summary statistics about notification delivery.",
)
async def get_notification_stats(db: AsyncSession = Depends(get_db)):
    """Get notification delivery statistics.

    Returns:
        Summary statistics including total sent, success rate, etc.
    """
    from sqlalchemy import func

    # Total notifications
    total_result = await db.execute(select(func.count(NotificationLog.id)))
    total = total_result.scalar() or 0

    # Successful notifications
    success_result = await db.execute(
        select(func.count(NotificationLog.id)).where(NotificationLog.success == True)
    )
    successful = success_result.scalar() or 0

    # Failed notifications
    failed_result = await db.execute(
        select(func.count(NotificationLog.id)).where(NotificationLog.success == False)
    )
    failed = failed_result.scalar() or 0

    # Success rate
    success_rate = (successful / total * 100) if total > 0 else 0.0

    # Notifications by event type
    event_counts_result = await db.execute(
        select(NotificationLog.event, func.count(NotificationLog.id))
        .group_by(NotificationLog.event)
        .order_by(func.count(NotificationLog.id).desc())
    )
    event_counts = {event: count for event, count in event_counts_result.all()}

    return {
        "total_sent": total,
        "successful": successful,
        "failed": failed,
        "success_rate": round(success_rate, 2),
        "by_event_type": event_counts,
    }
