"""e-Gov Law API client for fetching Japanese law text.

Integrates with the e-Gov Law API v2 to retrieve law text in XML format
and track amendments over time.
"""

import hashlib
import xml.etree.ElementTree as ET
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
    """Client for e-Gov Law API v2.

    Fetches law text in XML format and converts to plain text for LLM analysis.
    Tracks law amendments via the law history API.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.base_url = settings.egov_api_base_url

    async def check_for_changes(self, trigger: CrawlerRunTrigger = CrawlerRunTrigger.MANUAL) -> list[NtaPageChange]:
        """Check e-Gov API for law updates.

        Args:
            trigger: How this check was triggered.

        Returns:
            List of NtaPageChange objects for updated laws.
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
        target_laws = result.scalars().all()

        if not target_laws:
            logger.warning("No active e-Gov law target pages found")
            run.completed_at = datetime.now(UTC)
            await self.db.flush()
            return []

        changes: list[NtaPageChange] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            for law_page in target_laws:
                try:
                    change = await self._check_law(client, law_page, run.id)
                    run.pages_checked += 1
                    if change:
                        changes.append(change)
                        run.pages_changed += 1
                except Exception as e:
                    logger.exception(f"Failed to check law {law_page.name}")
                    run.pages_checked += 1
                    run.pages_failed += 1
                    await self._store_failed_snapshot(law_page, run.id, str(e))

        run.completed_at = datetime.now(UTC)
        await self.db.flush()

        logger.info(
            f"e-Gov law check complete: checked={run.pages_checked}, "
            f"changed={run.pages_changed}, failed={run.pages_failed}"
        )
        return changes

    async def _check_law(self, client: httpx.AsyncClient, law_page: NtaTargetPage, run_id: int) -> NtaPageChange | None:
        """Check a single law for updates.

        Args:
            client: HTTP client.
            law_page: Target law page (contains law ID in URL).
            run_id: Crawler run ID.

        Returns:
            NtaPageChange if law has been updated, None otherwise.
        """
        # Extract law ID from the page URL (stored in URL field)
        # URL format should be like: "egov://340AC0000000033" for 所得税法
        law_id = law_page.url.replace("egov://", "")

        logger.info(f"Fetching law {law_page.name} (ID: {law_id})")

        # Fetch law text from e-Gov API
        # Endpoint: GET /api/2/lawdata/{lawId}
        url = f"{self.base_url}/lawdata/{law_id}"
        response = await client.get(url)
        response.raise_for_status()

        # e-Gov API returns XML
        xml_content = response.text
        content_hash = hashlib.sha256(xml_content.encode()).hexdigest()

        # Get previous snapshot hash
        prev_result = await self.db.execute(
            select(NtaPageSnapshot)
            .where(
                NtaPageSnapshot.target_page_id == law_page.id,
                NtaPageSnapshot.status == SnapshotStatus.SUCCESS,
            )
            .order_by(NtaPageSnapshot.fetched_at.desc())
            .limit(1)
        )
        prev_snapshot = prev_result.scalar_one_or_none()
        prev_hash = prev_snapshot.content_hash if prev_snapshot else None

        # Convert XML to plain text for LLM consumption
        fit_markdown = self._xml_to_text(xml_content)

        # Store new snapshot
        snapshot = NtaPageSnapshot(
            target_page_id=law_page.id,
            crawler_run_id=run_id,
            content_hash=content_hash,
            raw_html=xml_content,  # Store XML as "raw_html"
            raw_markdown=None,
            fit_markdown=fit_markdown,
            status=SnapshotStatus.SUCCESS,
        )
        self.db.add(snapshot)
        await self.db.flush()

        # Check for change
        if prev_hash and prev_hash != content_hash:
            logger.info(f"Law update detected for {law_page.name}: {prev_hash[:8]}...{content_hash[:8]}")
            return NtaPageChange(
                page_name=law_page.name,
                page_url=law_page.url,
                previous_hash=prev_hash,
                new_hash=content_hash,
                snapshot_id=snapshot.id,
            )
        elif prev_hash is None:
            logger.info(f"First snapshot for law {law_page.name}: {content_hash[:8]}")

        return None

    def _xml_to_text(self, xml_content: str) -> str:
        """Convert e-Gov law XML to plain text.

        Args:
            xml_content: XML content from e-Gov API.

        Returns:
            Plain text representation suitable for LLM analysis.
        """
        try:
            root = ET.fromstring(xml_content)

            # Extract law name and number
            law_num = root.find(".//{http://laws.e-gov.go.jp/api/}LawNum")
            law_name = root.find(".//{http://laws.e-gov.go.jp/api/}LawTitle")

            lines = []
            if law_num is not None and law_num.text:
                lines.append(f"# Law Number: {law_num.text}")
            if law_name is not None and law_name.text:
                lines.append(f"# Law Name: {law_name.text}")
            lines.append("")

            # Extract main law body text
            # The structure varies, but we'll extract all text content
            for element in root.iter():
                if element.text and element.text.strip():
                    # Add element text with some structure
                    tag = element.tag.split("}")[-1]  # Remove namespace
                    if tag in ["Article", "Paragraph", "Item"]:
                        lines.append(f"\n## {tag}")
                    lines.append(element.text.strip())

            return "\n".join(lines)
        except ET.ParseError as e:
            logger.error(f"Failed to parse e-Gov XML: {e}")
            # Return raw XML if parsing fails
            return f"# Raw XML Content\n\n{xml_content}"

    async def _store_failed_snapshot(self, law_page: NtaTargetPage, run_id: int, error_message: str) -> None:
        """Store a failed snapshot in the database."""
        snapshot = NtaPageSnapshot(
            target_page_id=law_page.id,
            crawler_run_id=run_id,
            content_hash="",
            status=SnapshotStatus.FAILED,
            error_message=error_message,
        )
        self.db.add(snapshot)
        await self.db.flush()
