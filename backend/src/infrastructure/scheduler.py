"""Periodic crawler scheduling using APScheduler.

Runs the NTA crawler, MOF Tax Reform monitor, and e-Gov Law API client
at configurable intervals to detect regulation changes.
Also runs weekly deferred reminder notifications.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.notification_manager import NotificationManager
from src.config import settings
from src.domain.enums import CrawlerRunTrigger, EvolutionRunStatus
from src.infrastructure.egov_law_client import EgovLawClient
from src.infrastructure.models import EvolutionRun
from src.infrastructure.mof_reform_monitor import MofReformMonitor
from src.infrastructure.nta_monitor import NtaMonitor
from src.logging_config import get_logger

logger = get_logger(__name__)

scheduler = AsyncIOScheduler()

# TODO: Refactor to class-based scheduler for testability
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def scheduled_crawl() -> None:
    """Periodic NTA crawler job triggered by APScheduler."""
    if _session_factory is None:
        logger.error("Scheduler session factory not initialized")
        return

    async with _session_factory() as db:
        try:
            monitor = NtaMonitor(db)
            changes = await monitor.check_for_changes(trigger=CrawlerRunTrigger.SCHEDULED)
            await db.commit()
            if changes:
                logger.info(f"Scheduled NTA crawl detected {len(changes)} change(s)")
            else:
                logger.info("Scheduled NTA crawl: no changes detected")
        except Exception:
            await db.rollback()
            logger.exception("Scheduled NTA crawl failed")


async def scheduled_mof_crawl() -> None:
    """Periodic MOF Tax Reform crawler job triggered by APScheduler."""
    if _session_factory is None:
        logger.error("Scheduler session factory not initialized")
        return

    async with _session_factory() as db:
        try:
            monitor = MofReformMonitor(db)
            changes = await monitor.check_for_changes(trigger=CrawlerRunTrigger.SCHEDULED)
            await db.commit()
            if changes:
                logger.info(f"Scheduled MOF crawl detected {len(changes)} change(s)")
            else:
                logger.info("Scheduled MOF crawl: no changes detected")
        except Exception:
            await db.rollback()
            logger.exception("Scheduled MOF crawl failed")


async def scheduled_egov_crawl() -> None:
    """Periodic e-Gov Law API crawler job triggered by APScheduler."""
    if _session_factory is None:
        logger.error("Scheduler session factory not initialized")
        return

    async with _session_factory() as db:
        try:
            client = EgovLawClient(db)
            changes = await client.check_for_changes(trigger=CrawlerRunTrigger.SCHEDULED)
            await db.commit()
            if changes:
                logger.info(f"Scheduled e-Gov crawl detected {len(changes)} change(s)")
            else:
                logger.info("Scheduled e-Gov crawl: no changes detected")
        except Exception:
            await db.rollback()
            logger.exception("Scheduled e-Gov crawl failed")


async def scheduled_deferred_reminder() -> None:
    """Weekly deferred reminder job triggered by APScheduler."""
    if _session_factory is None:
        logger.error("Scheduler session factory not initialized")
        return

    async with _session_factory() as db:
        try:
            # Query all deferred runs
            result = await db.execute(
                select(EvolutionRun)
                .where(EvolutionRun.status == EvolutionRunStatus.DEFERRED)
                .order_by(EvolutionRun.started_at.desc())
            )
            deferred_runs = result.scalars().all()

            if not deferred_runs:
                logger.info("No deferred runs to remind about")
                return

            # Format deferred runs for email template
            deferred_list = [
                {
                    "id": run.id,
                    "summary": _get_run_summary(run),
                    "date": run.completed_at.strftime("%Y-%m-%d") if run.completed_at else "N/A",
                }
                for run in deferred_runs
            ]

            # Send reminder notification
            notifier = NotificationManager(db)
            await notifier.notify_deferred_reminder(
                deferred_count=len(deferred_runs),
                deferred_runs=deferred_list,
                dashboard_url="/admin/evolution/deferred",
            )

            logger.info(f"Sent deferred reminder for {len(deferred_runs)} run(s)")

        except Exception:
            logger.exception("Scheduled deferred reminder failed")


def _get_run_summary(run: EvolutionRun) -> str:
    """Extract a brief summary from a run's parsed changes.

    Args:
        run: EvolutionRun with parsed_changes

    Returns:
        Summary string or "Unknown change"
    """
    changes = run.parsed_changes.get("changes", []) if run.parsed_changes else []
    if not changes:
        return "Unknown change"

    first_change = changes[0]
    summary = first_change.get("summary", "")
    return summary or "Unknown change"


def start_scheduler(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Start the periodic crawler and notification schedulers.

    Args:
        session_factory: SQLAlchemy async session factory for DB access.
    """
    global _session_factory
    _session_factory = session_factory

    # NTA crawler job (daily)
    nta_interval_hours = settings.nta_crawl_interval_hours
    scheduler.add_job(
        scheduled_crawl,
        "interval",
        hours=nta_interval_hours,
        id="nta_crawler",
        replace_existing=True,
    )
    logger.info(f"NTA crawler scheduler started: every {nta_interval_hours} hour(s)")

    # MOF Tax Reform crawler job (weekly)
    mof_interval_hours = settings.mof_crawl_interval_hours
    scheduler.add_job(
        scheduled_mof_crawl,
        "interval",
        hours=mof_interval_hours,
        id="mof_crawler",
        replace_existing=True,
    )
    logger.info(f"MOF Tax Reform crawler scheduler started: every {mof_interval_hours} hour(s)")

    # e-Gov Law API crawler job (monthly)
    egov_interval_hours = settings.egov_crawl_interval_hours
    scheduler.add_job(
        scheduled_egov_crawl,
        "interval",
        hours=egov_interval_hours,
        id="egov_crawler",
        replace_existing=True,
    )
    logger.info(f"e-Gov Law API crawler scheduler started: every {egov_interval_hours} hour(s)")

    # Deferred reminder job (weekly on Monday at 9:00 AM)
    scheduler.add_job(
        scheduled_deferred_reminder,
        "cron",
        day_of_week="mon",
        hour=9,
        minute=0,
        id="deferred_reminder",
        replace_existing=True,
    )
    logger.info("Deferred reminder scheduler started: every Monday at 9:00 AM")

    scheduler.start()


def stop_scheduler() -> None:
    """Stop the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("NTA crawler scheduler stopped")
