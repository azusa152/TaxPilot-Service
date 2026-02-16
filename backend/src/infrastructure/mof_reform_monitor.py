"""MOF (Ministry of Finance) Tax Reform monitor.

Monitors the MOF Tax Reform outline page for new PDF documents,
downloads them, and converts them to markdown for LLM analysis.
"""

import hashlib
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import CrawlerRunTrigger, CrawlerSourceType, SnapshotStatus
from src.domain.schemas import NtaPageChange
from src.infrastructure.markitdown_adapter import MarkItDownAdapter
from src.infrastructure.models import NtaCrawlerRun, NtaPageSnapshot, NtaTargetPage
from src.logging_config import get_logger

logger = get_logger(__name__)

# Crawl4AI v0.8 configuration
BROWSER_CONFIG = BrowserConfig(headless=True)
CRAWL_CONFIG = CrawlerRunConfig(
    markdown_generator=DefaultMarkdownGenerator(content_filter=PruningContentFilter(threshold=0.4))
)


class MofReformMonitor:
    """Monitors MOF Tax Reform page for new PDF documents.

    Uses Crawl4AI to fetch the outline page, extracts PDF links from markdown,
    downloads new PDFs via httpx, and converts them to markdown via MarkItDown.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.markitdown = MarkItDownAdapter()

    async def check_for_changes(self, trigger: CrawlerRunTrigger = CrawlerRunTrigger.MANUAL) -> list[NtaPageChange]:
        """Check MOF Tax Reform page for new PDF documents.

        Args:
            trigger: How this check was triggered.

        Returns:
            List of NtaPageChange objects for new PDFs detected.
        """
        run = NtaCrawlerRun(trigger=trigger)
        self.db.add(run)
        await self.db.flush()

        # Get the MOF target page
        result = await self.db.execute(
            select(NtaTargetPage).where(
                NtaTargetPage.is_active == True,  # noqa: E712
                NtaTargetPage.source_type == CrawlerSourceType.MOF_TAX_REFORM,
            )
        )
        mof_page = result.scalar_one_or_none()

        if not mof_page:
            logger.warning("MOF Tax Reform target page not found")
            run.completed_at = datetime.now(UTC)
            await self.db.flush()
            return []

        changes: list[NtaPageChange] = []

        try:
            # Crawl the MOF outline page
            async with AsyncWebCrawler(config=BROWSER_CONFIG) as crawler:
                page_result = await crawler.arun(mof_page.url, config=CRAWL_CONFIG)

                if not page_result.success:
                    logger.error(f"Failed to crawl MOF page: {page_result.error_message}")
                    run.pages_checked = 1
                    run.pages_failed = 1
                    await self._store_failed_snapshot(mof_page, run.id, page_result.error_message or "Unknown error")
                else:
                    run.pages_checked = 1
                    # Extract PDF links from markdown
                    pdf_links = self._extract_pdf_links(page_result.markdown.fit_markdown, mof_page.url)
                    logger.info(f"Found {len(pdf_links)} PDF links on MOF page")

                    # Store page snapshot
                    page_hash = hashlib.sha256(page_result.markdown.fit_markdown.encode()).hexdigest()
                    page_snapshot = NtaPageSnapshot(
                        target_page_id=mof_page.id,
                        crawler_run_id=run.id,
                        content_hash=page_hash,
                        raw_html=page_result.html,
                        raw_markdown=page_result.markdown.raw_markdown,
                        fit_markdown=page_result.markdown.fit_markdown,
                        status=SnapshotStatus.SUCCESS,
                    )
                    self.db.add(page_snapshot)
                    await self.db.flush()

                    # Check for new PDFs
                    for pdf_url in pdf_links:
                        try:
                            change = await self._process_pdf(mof_page, pdf_url, run.id)
                            if change:
                                changes.append(change)
                                run.pages_changed += 1
                        except Exception:
                            logger.exception(f"Failed to process PDF {pdf_url}")
                            run.pages_failed += 1

        except Exception as e:
            logger.exception(f"MOF crawl failed: {e}")
            run.pages_failed = 1

        run.completed_at = datetime.now(UTC)
        await self.db.flush()

        logger.info(
            f"MOF crawler run complete: checked={run.pages_checked}, "
            f"changed={run.pages_changed}, failed={run.pages_failed}"
        )
        return changes

    def _extract_pdf_links(self, markdown: str, base_url: str) -> list[str]:
        """Extract PDF links from markdown content.

        Args:
            markdown: Markdown content from Crawl4AI.
            base_url: Base URL for resolving relative links.

        Returns:
            List of absolute PDF URLs.
        """
        # Match markdown links: [text](url) where url ends with .pdf
        pattern = r"\[([^\]]+)\]\(([^\)]+\.pdf)\)"
        matches = re.findall(pattern, markdown, re.IGNORECASE)

        pdf_links = []
        for _, url in matches:
            # Convert relative URLs to absolute
            if url.startswith("http"):
                pdf_links.append(url)
            elif url.startswith("/"):
                # Absolute path on same domain
                from urllib.parse import urlparse

                parsed = urlparse(base_url)
                pdf_links.append(f"{parsed.scheme}://{parsed.netloc}{url}")
            else:
                # Relative path
                base_path = base_url.rsplit("/", 1)[0]
                pdf_links.append(f"{base_path}/{url}")

        return list(set(pdf_links))  # Remove duplicates

    async def _process_pdf(self, parent_page: NtaTargetPage, pdf_url: str, run_id: int) -> NtaPageChange | None:
        """Download and process a PDF document.

        Args:
            parent_page: The MOF outline page.
            pdf_url: URL of the PDF to download.
            run_id: Crawler run ID.

        Returns:
            NtaPageChange if this is a new PDF, None otherwise.
        """
        # Check if we've seen this PDF before
        pdf_hash = hashlib.sha256(pdf_url.encode()).hexdigest()
        prev_result = await self.db.execute(
            select(NtaPageSnapshot)
            .where(
                NtaPageSnapshot.target_page_id == parent_page.id,
                NtaPageSnapshot.content_hash == pdf_hash,
                NtaPageSnapshot.status == SnapshotStatus.SUCCESS,
            )
            .limit(1)
        )
        if prev_result.scalar_one_or_none():
            logger.debug(f"PDF already processed: {pdf_url}")
            return None

        # Download PDF
        logger.info(f"Downloading new PDF: {pdf_url}")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(pdf_url, follow_redirects=True)
            response.raise_for_status()
            pdf_content = response.content

        # Save to temp file and convert to markdown
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            tmp_file.write(pdf_content)
            tmp_path = tmp_file.name

        try:
            pdf_markdown = self.markitdown.convert_to_markdown(tmp_path)
            logger.info(f"Converted PDF to markdown: {len(pdf_markdown)} chars")

            # Store snapshot with PDF content
            snapshot = NtaPageSnapshot(
                target_page_id=parent_page.id,
                crawler_run_id=run_id,
                content_hash=pdf_hash,
                raw_markdown=f"# PDF Source\n\nURL: {pdf_url}\n\n",
                fit_markdown=pdf_markdown,
                status=SnapshotStatus.SUCCESS,
            )
            self.db.add(snapshot)
            await self.db.flush()

            logger.info(f"New PDF detected: {pdf_url}")
            return NtaPageChange(
                page_name=f"{parent_page.name}_pdf",
                page_url=pdf_url,
                previous_hash=None,
                new_hash=pdf_hash,
                snapshot_id=snapshot.id,
            )
        finally:
            # Clean up temp file
            Path(tmp_path).unlink(missing_ok=True)

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
