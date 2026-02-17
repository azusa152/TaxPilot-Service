"""NTA crawler service — application layer.

Orchestrates crawl triggers, snapshot queries, target page CRUD, and health status.
"""

import asyncio
from typing import Literal

from sqlalchemy import func as sqla_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.enums import CrawlerRunTrigger
from src.domain.exceptions import NotFoundError
from src.domain.schemas import (
    CrawlerHealthStatus,
    CrawlerProgressResponse,
    CrawlerRunSummary,
    NtaPageChange,
    NtaSnapshotDetail,
    NtaTargetPageConfig,
)
from src.infrastructure.crawler_progress import get_progress_tracker
from src.infrastructure.egov_law_client import EgovLawClient
from src.infrastructure.models import NtaCrawlerRun, NtaPageSnapshot, NtaTargetPage
from src.infrastructure.mof_reform_monitor import MofReformMonitor
from src.infrastructure.nta_monitor import NtaMonitor
from src.logging_config import get_logger

logger = get_logger(__name__)


async def trigger_crawl(db: AsyncSession, trigger: CrawlerRunTrigger = CrawlerRunTrigger.MANUAL) -> list[NtaPageChange]:
    """Trigger NTA crawler run and return detected changes."""
    monitor = NtaMonitor(db)
    return await monitor.check_for_changes(trigger=trigger)


async def trigger_mof_crawl(
    db: AsyncSession, trigger: CrawlerRunTrigger = CrawlerRunTrigger.MANUAL
) -> list[NtaPageChange]:
    """Trigger MOF Tax Reform crawler run and return detected changes."""
    monitor = MofReformMonitor(db)
    return await monitor.check_for_changes(trigger=trigger)


async def trigger_egov_crawl(
    db: AsyncSession, trigger: CrawlerRunTrigger = CrawlerRunTrigger.MANUAL
) -> list[NtaPageChange]:
    """Trigger e-Gov Law API crawler run and return detected changes."""
    client = EgovLawClient(db)
    return await client.check_for_changes(trigger=trigger)


async def trigger_all_crawls(
    db: AsyncSession, trigger: CrawlerRunTrigger = CrawlerRunTrigger.MANUAL
) -> dict[str, list[NtaPageChange]]:
    """Trigger all three crawler types and return detected changes.

    Returns:
        Dict with keys: 'nta', 'mof', 'egov', each containing list of changes.
    """
    nta_changes = await trigger_crawl(db, trigger)
    mof_changes = await trigger_mof_crawl(db, trigger)
    egov_changes = await trigger_egov_crawl(db, trigger)

    return {
        "nta": nta_changes,
        "mof": mof_changes,
        "egov": egov_changes,
    }


async def get_health_status(db: AsyncSession) -> CrawlerHealthStatus:
    """Get overall crawler health status."""
    # Last run
    last_run_result = await db.execute(select(NtaCrawlerRun).order_by(NtaCrawlerRun.started_at.desc()).limit(1))
    last_run = last_run_result.scalar_one_or_none()

    # Count target pages
    total_result = await db.execute(select(sqla_func.count(NtaTargetPage.id)))
    total_pages = total_result.scalar_one()

    active_result = await db.execute(
        select(sqla_func.count(NtaTargetPage.id)).where(NtaTargetPage.is_active == True)  # noqa: E712
    )
    active_pages = active_result.scalar_one()

    # Determine health status
    if last_run is None:
        status = "degraded"
    elif last_run.pages_failed > 0 and last_run.pages_failed == last_run.pages_checked:
        status = "error"
    elif last_run.pages_failed > 0:
        status = "degraded"
    else:
        status = "healthy"

    last_run_summary = None
    if last_run:
        last_run_summary = CrawlerRunSummary(
            id=last_run.id,
            trigger=last_run.trigger,
            started_at=last_run.started_at,
            completed_at=last_run.completed_at,
            pages_checked=last_run.pages_checked,
            pages_changed=last_run.pages_changed,
            pages_failed=last_run.pages_failed,
        )

    return CrawlerHealthStatus(
        status=status,
        last_run=last_run_summary,
        next_scheduled_run=None,
        total_target_pages=total_pages,
        active_target_pages=active_pages,
    )


async def list_snapshots(
    db: AsyncSession,
    page_name: str | None = None,
    changes_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[NtaSnapshotDetail]:
    """List snapshots with optional filters."""
    query = (
        select(NtaPageSnapshot, NtaTargetPage)
        .join(NtaTargetPage, NtaPageSnapshot.target_page_id == NtaTargetPage.id)
        .order_by(NtaPageSnapshot.fetched_at.desc())
    )

    if page_name:
        query = query.where(NtaTargetPage.name == page_name)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    rows = result.all()

    snapshots = []
    for snapshot, target_page in rows:
        snapshots.append(
            NtaSnapshotDetail(
                id=snapshot.id,
                target_page_name=target_page.name,
                target_page_url=target_page.url,
                source_type=target_page.source_type,
                content_hash=snapshot.content_hash,
                raw_markdown=snapshot.raw_markdown,
                fit_markdown=snapshot.fit_markdown,
                extracted_tables=snapshot.extracted_tables,
                status=snapshot.status,
                error_message=snapshot.error_message,
                response_time_ms=snapshot.response_time_ms,
                fetched_at=snapshot.fetched_at,
            )
        )

    if changes_only:
        # NOTE: This filtering is applied in Python after limit/offset, which means
        # the result set may contain fewer items than `limit`. For MVP this is
        # acceptable. A future improvement could use a SQL window function (LAG())
        # to compare with the previous hash per page before applying pagination.
        seen_hashes: dict[str, str] = {}
        filtered = []
        # Process in chronological order for change detection, then reverse
        for s in reversed(snapshots):
            prev = seen_hashes.get(s.target_page_name)
            if prev is None or prev != s.content_hash:
                filtered.append(s)
            seen_hashes[s.target_page_name] = s.content_hash
        filtered.reverse()
        return filtered

    return snapshots


async def get_snapshot_detail(db: AsyncSession, snapshot_id: int) -> NtaSnapshotDetail:
    """Get full snapshot detail including markdown content."""
    result = await db.execute(
        select(NtaPageSnapshot, NtaTargetPage)
        .join(NtaTargetPage, NtaPageSnapshot.target_page_id == NtaTargetPage.id)
        .where(NtaPageSnapshot.id == snapshot_id)
    )
    row = result.one_or_none()
    if row is None:
        raise NotFoundError(f"Snapshot {snapshot_id} not found")

    snapshot, target_page = row
    return NtaSnapshotDetail(
        id=snapshot.id,
        target_page_name=target_page.name,
        target_page_url=target_page.url,
        source_type=target_page.source_type,
        content_hash=snapshot.content_hash,
        raw_markdown=snapshot.raw_markdown,
        fit_markdown=snapshot.fit_markdown,
        extracted_tables=snapshot.extracted_tables,
        status=snapshot.status,
        error_message=snapshot.error_message,
        response_time_ms=snapshot.response_time_ms,
        fetched_at=snapshot.fetched_at,
    )


async def get_snapshot_markdown(db: AsyncSession, snapshot_id: int) -> str:
    """Get just the fit_markdown for a snapshot (for copy/paste)."""
    result = await db.execute(
        select(NtaPageSnapshot.id, NtaPageSnapshot.fit_markdown).where(NtaPageSnapshot.id == snapshot_id)
    )
    row = result.one_or_none()
    if row is None:
        raise NotFoundError(f"Snapshot {snapshot_id} not found")
    if row.fit_markdown is None:
        raise NotFoundError(f"Snapshot {snapshot_id} has no markdown content (status may be FAILED)")
    return row.fit_markdown


async def upsert_target_page(db: AsyncSession, config: NtaTargetPageConfig) -> NtaTargetPage:
    """Add or update a target NTA page."""
    result = await db.execute(select(NtaTargetPage).where(NtaTargetPage.name == config.name))
    existing = result.scalar_one_or_none()

    if existing:
        existing.url = config.url
        existing.description = config.description
        existing.is_active = config.is_active
        existing.check_interval_hours = config.check_interval_hours
        existing.source_type = config.source_type
        await db.flush()
        return existing

    page = NtaTargetPage(
        name=config.name,
        url=config.url,
        description=config.description,
        is_active=config.is_active,
        check_interval_hours=config.check_interval_hours,
        source_type=config.source_type,
    )
    db.add(page)
    await db.flush()
    return page


async def list_target_pages(db: AsyncSession) -> list[NtaTargetPage]:
    """List all target pages."""
    result = await db.execute(select(NtaTargetPage).order_by(NtaTargetPage.name))
    return list(result.scalars().all())


async def list_crawler_runs(db: AsyncSession, limit: int = 20) -> list[CrawlerRunSummary]:
    """List recent crawler runs."""
    result = await db.execute(select(NtaCrawlerRun).order_by(NtaCrawlerRun.started_at.desc()).limit(limit))
    runs = result.scalars().all()
    return [
        CrawlerRunSummary(
            id=run.id,
            trigger=run.trigger,
            started_at=run.started_at,
            completed_at=run.completed_at,
            pages_checked=run.pages_checked,
            pages_changed=run.pages_changed,
            pages_failed=run.pages_failed,
        )
        for run in runs
    ]


# --- Background Crawl Orchestration ---


async def start_background_crawl(
    session_factory: async_sessionmaker[AsyncSession],
    layer: Literal["nta", "mof", "egov", "all"],
    trigger: CrawlerRunTrigger = CrawlerRunTrigger.MANUAL,
) -> dict[str, str]:
    """Start a crawler layer in the background.

    Args:
        session_factory: Async session factory for DB access.
        layer: Layer to crawl ('nta', 'mof', 'egov', or 'all').
        trigger: Trigger type (MANUAL or SCHEDULED).

    Returns:
        Dict with 'status' and 'message' keys.
    """
    progress_tracker = get_progress_tracker()

    async def run_crawl() -> None:
        """Background task to run the crawler."""
        async with session_factory() as db:
            try:
                if layer == "nta":
                    monitor = NtaMonitor(db, progress_tracker=progress_tracker)
                    await monitor.check_for_changes(trigger=trigger)
                elif layer == "mof":
                    monitor = MofReformMonitor(db, progress_tracker=progress_tracker)
                    await monitor.check_for_changes(trigger=trigger)
                elif layer == "egov":
                    client = EgovLawClient(db, progress_tracker=progress_tracker)
                    await client.check_for_changes(trigger=trigger)
                elif layer == "all":
                    nta_monitor = NtaMonitor(db, progress_tracker=progress_tracker)
                    await nta_monitor.check_for_changes(trigger=trigger)
                    await db.commit()

                    mof_monitor = MofReformMonitor(db, progress_tracker=progress_tracker)
                    await mof_monitor.check_for_changes(trigger=trigger)
                    await db.commit()

                    egov_client = EgovLawClient(db, progress_tracker=progress_tracker)
                    await egov_client.check_for_changes(trigger=trigger)

                await db.commit()
                logger.info(f"Background crawl completed for layer: {layer}")
            except Exception:
                await db.rollback()
                logger.exception(f"Background crawl failed for layer: {layer}")

    # Start background task
    asyncio.create_task(run_crawl())

    return {"status": "STARTED", "message": f"Crawler for layer '{layer}' started in background"}


async def get_crawler_progress() -> CrawlerProgressResponse:
    """Get current crawler progress for all layers.

    Returns:
        CrawlerProgressResponse with all layer states.
    """
    progress_tracker = get_progress_tracker()
    return await progress_tracker.get_progress()
