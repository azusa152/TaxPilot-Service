"""Periodic crawler scheduling using APScheduler.

Runs the NTA crawler at configurable intervals to detect regulation changes.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import settings
from src.domain.enums import CrawlerRunTrigger
from src.infrastructure.nta_monitor import NtaMonitor
from src.logging_config import get_logger

logger = get_logger(__name__)

scheduler = AsyncIOScheduler()

# TODO: Refactor to class-based scheduler for testability
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def scheduled_crawl() -> None:
    """Periodic crawler job triggered by APScheduler."""
    if _session_factory is None:
        logger.error("Scheduler session factory not initialized")
        return

    async with _session_factory() as db:
        try:
            monitor = NtaMonitor(db, rate_limit_seconds=settings.nta_crawl_rate_limit_seconds)
            changes = await monitor.check_for_changes(trigger=CrawlerRunTrigger.SCHEDULED)
            await db.commit()
            if changes:
                logger.info(f"Scheduled crawl detected {len(changes)} change(s)")
            else:
                logger.info("Scheduled crawl: no changes detected")
        except Exception:
            await db.rollback()
            logger.exception("Scheduled crawl failed")


def start_scheduler(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Start the periodic crawler scheduler.

    Args:
        session_factory: SQLAlchemy async session factory for DB access.
    """
    global _session_factory
    _session_factory = session_factory

    interval_hours = settings.nta_crawl_interval_hours

    scheduler.add_job(
        scheduled_crawl,
        "interval",
        hours=interval_hours,
        id="nta_crawler",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"NTA crawler scheduler started: every {interval_hours} hour(s)")


def stop_scheduler() -> None:
    """Stop the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("NTA crawler scheduler stopped")
