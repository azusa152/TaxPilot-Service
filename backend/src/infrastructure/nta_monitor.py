"""NTA (National Tax Agency) law change monitor using Crawl4AI.

Crawls NTA pages, converts to markdown (raw + LLM-optimized), stores
snapshots in the database, and detects content changes via hash comparison.
"""

import asyncio
import hashlib
import time
from datetime import datetime, timezone

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import CrawlerRunTrigger, SnapshotStatus
from src.domain.schemas import NtaPageChange
from src.infrastructure.models import NtaCrawlerRun, NtaPageSnapshot, NtaTargetPage
from src.logging_config import get_logger

logger = get_logger(__name__)

# Crawl4AI configuration for NTA pages
CRAWL_CONFIG = CrawlerRunConfig(
    markdown_generator=DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(threshold=0.4)
    )
)


class NtaMonitor:
    """Monitors NTA pages for regulation changes using Crawl4AI.

    Stores both raw and LLM-optimized markdown in the database.
    Uses fit_markdown hash for change detection (more stable than HTML hash).
    """

    def __init__(self, db: AsyncSession, rate_limit_seconds: float = 2.0):
        self.db = db
        self.rate_limit_seconds = rate_limit_seconds

    async def check_for_changes(
        self, trigger: CrawlerRunTrigger = CrawlerRunTrigger.MANUAL
    ) -> list[NtaPageChange]:
        """Crawl all active target pages and detect changes.

        Args:
            trigger: How this check was triggered.

        Returns:
            List of NtaPageChange objects for pages where content changed.
        """
        run = NtaCrawlerRun(trigger=trigger)
        self.db.add(run)
        await self.db.flush()

        result = await self.db.execute(
            select(NtaTargetPage).where(NtaTargetPage.is_active == True)  # noqa: E712
        )
        target_pages = result.scalars().all()

        changes: list[NtaPageChange] = []

        async with AsyncWebCrawler() as crawler:
            for page in target_pages:
                try:
                    change = await self._check_page(crawler, page, run.id)
                    run.pages_checked += 1
                    if change:
                        changes.append(change)
                        run.pages_changed += 1
                except Exception as e:
                    logger.exception(f"Failed to crawl {page.name}")
                    run.pages_checked += 1
                    run.pages_failed += 1
                    snapshot = NtaPageSnapshot(
                        target_page_id=page.id,
                        crawler_run_id=run.id,
                        content_hash="",
                        status=SnapshotStatus.FAILED,
                        error_message=str(e),
                    )
                    self.db.add(snapshot)

                # Rate limiting between pages
                await asyncio.sleep(self.rate_limit_seconds)

        run.completed_at = datetime.now(timezone.utc)
        await self.db.flush()

        logger.info(
            f"Crawler run complete: checked={run.pages_checked}, "
            f"changed={run.pages_changed}, failed={run.pages_failed}"
        )
        return changes

    async def _check_page(
        self,
        crawler: AsyncWebCrawler,
        page: NtaTargetPage,
        run_id: int,
    ) -> NtaPageChange | None:
        """Crawl a single page and check for changes.

        Returns NtaPageChange if content has changed, None otherwise.
        """
        start = time.time()
        result = await crawler.arun(page.url, config=CRAWL_CONFIG)
        response_time_ms = int((time.time() - start) * 1000)

        raw_md = result.markdown.raw_markdown
        fit_md = result.markdown.fit_markdown
        content_hash = hashlib.sha256(fit_md.encode()).hexdigest()

        # Get previous snapshot hash
        prev_result = await self.db.execute(
            select(NtaPageSnapshot)
            .where(
                NtaPageSnapshot.target_page_id == page.id,
                NtaPageSnapshot.status == SnapshotStatus.SUCCESS,
            )
            .order_by(NtaPageSnapshot.fetched_at.desc())
            .limit(1)
        )
        prev_snapshot = prev_result.scalar_one_or_none()
        prev_hash = prev_snapshot.content_hash if prev_snapshot else None

        # TODO(Phase 6B): Extract structured table data from CrawlResult
        # once Crawl4AI exposes a tables API, and populate extracted_tables.

        # Store new snapshot
        snapshot = NtaPageSnapshot(
            target_page_id=page.id,
            crawler_run_id=run_id,
            content_hash=content_hash,
            raw_html=result.html,
            raw_markdown=raw_md,
            fit_markdown=fit_md,
            status=SnapshotStatus.SUCCESS,
            response_time_ms=response_time_ms,
        )
        self.db.add(snapshot)
        await self.db.flush()

        # Check for change
        if prev_hash and prev_hash != content_hash:
            logger.info(f"Change detected on {page.name}: {prev_hash[:8]}...{content_hash[:8]}")
            return NtaPageChange(
                page_name=page.name,
                page_url=page.url,
                previous_hash=prev_hash,
                new_hash=content_hash,
                snapshot_id=snapshot.id,
            )
        elif prev_hash is None:
            logger.info(f"First snapshot for {page.name}: {content_hash[:8]}")

        return None
