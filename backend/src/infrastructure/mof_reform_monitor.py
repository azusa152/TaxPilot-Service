"""MOF (Ministry of Finance) Tax Reform Monitor.

Monitors the MOF Tax Reform outline page for new PDF releases.
Uses httpx + BeautifulSoup to extract PDF links and MarkItDown to convert PDFs to Markdown.
Stores results in the same NtaPageSnapshot table with source_type='MOF_TAX_REFORM'.
"""

import hashlib
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import CrawlPageStatus, CrawlerRunTrigger, CrawlerSourceType, SnapshotStatus
from src.domain.schemas import NtaPageChange
from src.infrastructure.markitdown_adapter import MarkItDownAdapter
from src.infrastructure.models import NtaCrawlerRun, NtaPageSnapshot, NtaTargetPage
from src.logging_config import get_logger

logger = get_logger(__name__)

# Avoid circular import by making progress tracker optional
try:
    from src.infrastructure.crawler_progress import CrawlerProgressTracker
except ImportError:
    CrawlerProgressTracker = None  # type: ignore


class MofReformMonitor:
    """Monitors MOF Tax Reform outline page for new PDF releases.

    Uses httpx to fetch HTML, BeautifulSoup to extract PDF links, and MarkItDown
    to convert PDFs to Markdown. Detects changes by hashing the list of PDF links.
    """

    def __init__(self, db: AsyncSession, progress_tracker: "CrawlerProgressTracker | None" = None):
        self.db = db
        self.markitdown = MarkItDownAdapter()
        self.progress_tracker = progress_tracker

    async def check_for_changes(self, trigger: CrawlerRunTrigger = CrawlerRunTrigger.MANUAL) -> list[NtaPageChange]:
        """Crawl MOF Tax Reform outline page and detect changes.

        Args:
            trigger: How this check was triggered.

        Returns:
            List of NtaPageChange objects for pages where content changed.
        """
        run = NtaCrawlerRun(trigger=trigger)
        self.db.add(run)
        await self.db.flush()

        # Get all MOF target pages
        result = await self.db.execute(
            select(NtaTargetPage).where(
                NtaTargetPage.is_active == True,  # noqa: E712
                NtaTargetPage.source_type == CrawlerSourceType.MOF_TAX_REFORM,
            )
        )
        target_pages = result.scalars().all()

        if not target_pages:
            logger.warning("No active MOF target pages found")
            run.completed_at = datetime.now(UTC)
            await self.db.flush()
            return []

        # Initialize progress tracking
        if self.progress_tracker:
            await self.progress_tracker.start_layer(
                "MOF_TAX_REFORM",
                run.id,
                [(page.name, page.url) for page in target_pages],
            )

        changes: list[NtaPageChange] = []

        for page in target_pages:
            run.pages_checked += 1
            start_time = time.time()
            
            # Update progress: mark as CRAWLING
            if self.progress_tracker:
                await self.progress_tracker.update_page(
                    "MOF_TAX_REFORM", page.name, CrawlPageStatus.CRAWLING
                )

            try:
                change = await self._process_mof_page(page, run.id, start_time)
                if change:
                    changes.append(change)
                    run.pages_changed += 1
                
                # Update progress: mark as SUCCESS
                if self.progress_tracker:
                    response_time_ms = int((time.time() - start_time) * 1000)
                    await self.progress_tracker.update_page(
                        "MOF_TAX_REFORM",
                        page.name,
                        CrawlPageStatus.SUCCESS,
                        response_time_ms=response_time_ms,
                        changed=change is not None,
                    )
            except Exception as e:
                logger.exception(f"Failed to process MOF page {page.name}: {e}")
                run.pages_failed += 1
                await self._store_failed_snapshot(page, run.id, str(e))
                
                # Update progress: mark as FAILED
                if self.progress_tracker:
                    await self.progress_tracker.update_page(
                        "MOF_TAX_REFORM",
                        page.name,
                        CrawlPageStatus.FAILED,
                        error_message=str(e),
                    )

        run.completed_at = datetime.now(UTC)
        await self.db.flush()

        # Mark layer as completed in progress tracker
        if self.progress_tracker:
            await self.progress_tracker.complete_layer("MOF_TAX_REFORM")

        logger.info(
            f"MOF crawler run complete: checked={run.pages_checked}, "
            f"changed={run.pages_changed}, failed={run.pages_failed}"
        )
        return changes

    async def _process_mof_page(self, page: NtaTargetPage, run_id: int, start_time: float) -> NtaPageChange | None:
        """Process a single MOF outline page and check for changes.

        Returns NtaPageChange if content has changed, None otherwise.
        """
        # Fetch HTML
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(page.url)
            response.raise_for_status()
            html_content = response.text

        # Extract PDF links using BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")
        pdf_links = self._extract_pdf_links(soup, page.url)

        if not pdf_links:
            logger.warning(f"No PDF links found on {page.name}")

        # Hash the list of PDF URLs for change detection
        pdf_links_str = "\n".join(sorted(pdf_links))
        page_hash = hashlib.sha256(pdf_links_str.encode()).hexdigest()

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

        # Download and convert the first PDF (or all PDFs if needed)
        # For MVP, we'll just convert the first PDF found
        fit_markdown = ""
        if pdf_links:
            fit_markdown = await self._download_and_convert_pdf(pdf_links[0])

        response_time_ms = int((time.time() - start_time) * 1000)

        # Store new snapshot
        snapshot = NtaPageSnapshot(
            target_page_id=page.id,
            crawler_run_id=run_id,
            content_hash=page_hash,
            raw_html=html_content,
            raw_markdown=pdf_links_str,  # Store list of PDF URLs
            fit_markdown=fit_markdown,
            extracted_tables={"pdf_links": pdf_links},
            status=SnapshotStatus.SUCCESS,
            response_time_ms=response_time_ms,
        )
        self.db.add(snapshot)
        await self.db.flush()

        # Check for change
        if prev_hash and prev_hash != page_hash:
            logger.info(f"MOF change detected on {page.name}: {prev_hash[:8]}...{page_hash[:8]}")
            return NtaPageChange(
                page_name=page.name,
                page_url=page.url,
                previous_hash=prev_hash,
                new_hash=page_hash,
                snapshot_id=snapshot.id,
            )
        elif prev_hash is None:
            logger.info(f"First MOF snapshot for {page.name}: {page_hash[:8]}")

        return None

    def _extract_pdf_links(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """Extract all PDF links from the HTML.

        Args:
            soup: BeautifulSoup parsed HTML.
            base_url: Base URL for resolving relative links.

        Returns:
            List of absolute PDF URLs.
        """
        pdf_links = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.endswith(".pdf"):
                # Resolve relative URLs
                if not href.startswith("http"):
                    from urllib.parse import urljoin

                    href = urljoin(base_url, href)
                pdf_links.append(href)
        return pdf_links

    async def _download_and_convert_pdf(self, pdf_url: str) -> str:
        """Download a PDF and convert it to Markdown.

        Args:
            pdf_url: URL of the PDF to download.

        Returns:
            Markdown content.
        """
        try:
            # Download PDF to temp file
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(pdf_url)
                response.raise_for_status()

                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                    temp_file.write(response.content)
                    temp_path = temp_file.name

            # Convert to Markdown
            markdown = self.markitdown.convert_to_markdown(temp_path)

            # Clean up temp file
            Path(temp_path).unlink()

            return markdown

        except Exception as e:
            logger.error(f"Failed to download/convert PDF {pdf_url}: {e}")
            return f"[PDF conversion failed: {e}]"

    async def _store_failed_snapshot(self, page: NtaTargetPage, run_id: int, error_message: str) -> None:
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
