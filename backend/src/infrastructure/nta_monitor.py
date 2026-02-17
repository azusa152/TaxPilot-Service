"""NTA (National Tax Agency) law change monitor using Crawl4AI.

Crawls NTA pages, converts to markdown (raw + LLM-optimized), stores
snapshots in the database, and detects content changes via hash comparison.
"""

import hashlib
import time
from datetime import datetime, timezone

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlResult, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import CrawlPageStatus, CrawlerRunTrigger, CrawlerSourceType, SnapshotStatus
from src.domain.schemas import NtaPageChange
from src.infrastructure.models import NtaCrawlerRun, NtaPageSnapshot, NtaTargetPage
from src.logging_config import get_logger

logger = get_logger(__name__)

# Avoid circular import by making progress tracker optional
try:
    from src.infrastructure.crawler_progress import CrawlerProgressTracker
except ImportError:
    CrawlerProgressTracker = None  # type: ignore

# Crawl4AI v0.8 configuration
BROWSER_CONFIG = BrowserConfig(headless=True)
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

    def __init__(self, db: AsyncSession, progress_tracker: "CrawlerProgressTracker | None" = None):
        self.db = db
        self.progress_tracker = progress_tracker

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
            select(NtaTargetPage).where(
                NtaTargetPage.is_active == True,  # noqa: E712
                NtaTargetPage.source_type == CrawlerSourceType.NTA_TAX_ANSWER,
            )
        )
        target_pages = result.scalars().all()

        if not target_pages:
            logger.warning("No active target pages found")
            run.completed_at = datetime.now(timezone.utc)
            await self.db.flush()
            return []

        # Initialize progress tracking
        if self.progress_tracker:
            await self.progress_tracker.start_layer(
                "NTA_TAX_ANSWER",
                run.id,
                [(page.name, page.url) for page in target_pages],
            )

        changes: list[NtaPageChange] = []
        
        # Use arun_many for batch crawling with built-in rate limiting
        async with AsyncWebCrawler(config=BROWSER_CONFIG) as crawler:
            urls = [page.url for page in target_pages]
            start_times = {page.url: time.time() for page in target_pages}
            
            try:
                results = await crawler.arun_many(
                    urls=urls,
                    config=CRAWL_CONFIG,
                )
                
                # Process results and match with target pages
                for page, result in zip(target_pages, results):
                    run.pages_checked += 1
                    
                    # Update progress: mark as CRAWLING
                    if self.progress_tracker:
                        await self.progress_tracker.update_page(
                            "NTA_TAX_ANSWER", page.name, CrawlPageStatus.CRAWLING
                        )
                    
                    response_time_ms = int((time.time() - start_times[page.url]) * 1000)
                    
                    if result.success:
                        try:
                            change = await self._process_successful_crawl(
                                page, result, run.id, response_time_ms
                            )
                            if change:
                                changes.append(change)
                                run.pages_changed += 1
                            
                            # Update progress: mark as SUCCESS
                            if self.progress_tracker:
                                await self.progress_tracker.update_page(
                                    "NTA_TAX_ANSWER",
                                    page.name,
                                    CrawlPageStatus.SUCCESS,
                                    response_time_ms=response_time_ms,
                                    changed=change is not None,
                                )
                        except Exception as e:
                            logger.exception(f"Failed to process result for {page.name}")
                            run.pages_failed += 1
                            await self._store_failed_snapshot(page, run.id, str(e))
                            
                            # Update progress: mark as FAILED
                            if self.progress_tracker:
                                await self.progress_tracker.update_page(
                                    "NTA_TAX_ANSWER",
                                    page.name,
                                    CrawlPageStatus.FAILED,
                                    error_message=str(e),
                                )
                    else:
                        logger.error(f"Crawl failed for {page.name}: {result.error_message}")
                        run.pages_failed += 1
                        await self._store_failed_snapshot(page, run.id, result.error_message or "Unknown error")
                        
                        # Update progress: mark as FAILED
                        if self.progress_tracker:
                            await self.progress_tracker.update_page(
                                "NTA_TAX_ANSWER",
                                page.name,
                                CrawlPageStatus.FAILED,
                                error_message=result.error_message or "Unknown error",
                            )
                        
            except Exception as e:
                logger.exception(f"Batch crawl failed: {e}")
                run.pages_failed = run.pages_checked
                if self.progress_tracker:
                    await self.progress_tracker.fail_layer("NTA_TAX_ANSWER", str(e))

        run.completed_at = datetime.now(timezone.utc)
        await self.db.flush()

        # Mark layer as completed in progress tracker
        if self.progress_tracker:
            await self.progress_tracker.complete_layer("NTA_TAX_ANSWER")

        logger.info(
            f"Crawler run complete: checked={run.pages_checked}, "
            f"changed={run.pages_changed}, failed={run.pages_failed}"
        )
        return changes

    async def _process_successful_crawl(
        self,
        page: NtaTargetPage,
        result: CrawlResult,
        run_id: int,
        response_time_ms: int,
    ) -> NtaPageChange | None:
        """Process a successful crawl result and check for changes.

        Returns NtaPageChange if content has changed, None otherwise.
        """
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
    
    async def _store_failed_snapshot(
        self, page: NtaTargetPage, run_id: int, error_message: str
    ) -> None:
        """Store a failed snapshot in the database."""
        snapshot = NtaPageSnapshot(
            target_page_id=page.id,
            crawler_run_id=run_id,
            content_hash="",
            status=SnapshotStatus.FAILED,
            error_message=error_message,
        )
        self.db.add(snapshot)
        await self.db.flush()
