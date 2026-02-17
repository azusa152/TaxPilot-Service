"""e-Gov Law API Client for fetching Japanese tax law XML.

Monitors specific laws (Income Tax Act, Local Tax Act) via the e-Gov Law API v2.
Stores XML as raw_html and extracts plain text/markdown as fit_markdown.
Uses the same NtaPageSnapshot table with source_type='EGOV_LAW'.
"""

import hashlib
import re
import time
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.domain.enums import CrawlerRunTrigger, CrawlerSourceType, SnapshotStatus
from src.domain.schemas import NtaPageChange
from src.infrastructure.models import NtaCrawlerRun, NtaPageSnapshot, NtaTargetPage
from src.logging_config import get_logger

logger = get_logger(__name__)


class EgovLawClient:
    """e-Gov Law API client for fetching Japanese tax laws.

    Uses the e-Gov Law API v2 to fetch XML representations of tax laws.
    Detects changes by comparing XML content hashes.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.api_base = settings.egov_api_base_url

    async def check_for_changes(self, trigger: CrawlerRunTrigger = CrawlerRunTrigger.MANUAL) -> list[NtaPageChange]:
        """Fetch e-Gov law data and detect changes.

        Args:
            trigger: How this check was triggered.

        Returns:
            List of NtaPageChange objects for laws where content changed.
        """
        run = NtaCrawlerRun(trigger=trigger)
        self.db.add(run)
        await self.db.flush()

        # Get all e-Gov target pages
        result = await self.db.execute(
            select(NtaTargetPage).where(
                NtaTargetPage.is_active == True,  # noqa: E712
                NtaTargetPage.source_type == CrawlerSourceType.EGOV_LAW,
            )
        )
        target_pages = result.scalars().all()

        if not target_pages:
            logger.warning("No active e-Gov target pages found")
            run.completed_at = datetime.now(UTC)
            await self.db.flush()
            return []

        changes: list[NtaPageChange] = []

        for page in target_pages:
            run.pages_checked += 1
            start_time = time.time()

            try:
                change = await self._process_egov_law(page, run.id, start_time)
                if change:
                    changes.append(change)
                    run.pages_changed += 1
            except Exception as e:
                logger.exception(f"Failed to process e-Gov law {page.name}: {e}")
                run.pages_failed += 1
                await self._store_failed_snapshot(page, run.id, str(e))

        run.completed_at = datetime.now(UTC)
        await self.db.flush()

        logger.info(
            f"e-Gov crawler run complete: checked={run.pages_checked}, "
            f"changed={run.pages_changed}, failed={run.pages_failed}"
        )
        return changes

    async def _process_egov_law(self, page: NtaTargetPage, run_id: int, start_time: float) -> NtaPageChange | None:
        """Process a single e-Gov law and check for changes.

        Returns NtaPageChange if content has changed, None otherwise.
        """
        # Extract law ID from egov:// URL
        law_id = self._extract_law_id(page.url)
        if not law_id:
            raise ValueError(f"Invalid egov:// URL format: {page.url}")

        # Fetch XML from e-Gov API
        xml_content = await self._fetch_law_xml(law_id)

        # Hash the XML for change detection
        content_hash = hashlib.sha256(xml_content.encode()).hexdigest()

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

        # Extract plain text for fit_markdown
        fit_markdown = self._xml_to_markdown(xml_content)

        response_time_ms = int((time.time() - start_time) * 1000)

        # Store new snapshot
        snapshot = NtaPageSnapshot(
            target_page_id=page.id,
            crawler_run_id=run_id,
            content_hash=content_hash,
            raw_html=xml_content,  # Store XML as raw_html
            raw_markdown=None,
            fit_markdown=fit_markdown,
            extracted_tables=None,
            status=SnapshotStatus.SUCCESS,
            response_time_ms=response_time_ms,
        )
        self.db.add(snapshot)
        await self.db.flush()

        # Check for change
        if prev_hash and prev_hash != content_hash:
            logger.info(f"e-Gov change detected on {page.name}: {prev_hash[:8]}...{content_hash[:8]}")
            return NtaPageChange(
                page_name=page.name,
                page_url=page.url,
                previous_hash=prev_hash,
                new_hash=content_hash,
                snapshot_id=snapshot.id,
            )
        elif prev_hash is None:
            logger.info(f"First e-Gov snapshot for {page.name}: {content_hash[:8]}")

        return None

    def _extract_law_id(self, egov_url: str) -> str | None:
        """Extract law ID from egov:// URL.

        Args:
            egov_url: URL in format egov://LAW_ID

        Returns:
            Law ID or None if invalid format.
        """
        if egov_url.startswith("egov://"):
            return egov_url.replace("egov://", "")
        return None

    async def _fetch_law_xml(self, law_id: str) -> str:
        """Fetch law XML from e-Gov API.

        Args:
            law_id: e-Gov law identifier.

        Returns:
            XML content as string.

        Raises:
            httpx.HTTPError: If API request fails.
        """
        url = f"{self.api_base}/lawdata/{law_id}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    def _xml_to_markdown(self, xml_content: str) -> str:
        """Convert e-Gov law XML to plain text/markdown.

        This is a simple text extraction. A more sophisticated implementation
        could parse the XML structure and preserve article/section hierarchy.

        Args:
            xml_content: XML string from e-Gov API.

        Returns:
            Plain text representation.
        """
        # Remove XML tags (simple regex-based approach)
        # A proper implementation would use xml.etree.ElementTree to parse structure
        text = re.sub(r"<[^>]+>", " ", xml_content)

        # Clean up whitespace
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

        # Add basic structure markers (this is a placeholder - improve as needed)
        lines = text.split(". ")
        markdown = "\n\n".join(line.strip() for line in lines if line.strip())

        return markdown

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
