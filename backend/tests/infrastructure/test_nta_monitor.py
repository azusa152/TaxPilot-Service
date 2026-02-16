"""Tests for infrastructure/nta_monitor.py — NtaMonitor with Crawl4AI."""

import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from src.domain.enums import CrawlerRunTrigger, SnapshotStatus
from src.infrastructure.models import NtaCrawlerRun, NtaPageSnapshot, NtaTargetPage
from src.infrastructure.nta_monitor import NtaMonitor


def _make_crawl_result(
    raw_markdown: str = "# Raw content",
    fit_markdown: str = "# Fit content",
    html: str = "<html><body>Hello</body></html>",
):
    """Create a mock Crawl4AI CrawlResult."""
    markdown = SimpleNamespace(raw_markdown=raw_markdown, fit_markdown=fit_markdown)
    return SimpleNamespace(markdown=markdown, html=html)


@pytest.fixture()
async def db_with_target(db_session):
    """DB session with an active target page."""
    page = NtaTargetPage(
        name="income_tax_rates",
        url="https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2260.htm",
        description="Income tax rate table",
        is_active=True,
        check_interval_hours=24,
    )
    db_session.add(page)
    await db_session.flush()
    return db_session


@pytest.fixture()
async def db_with_two_targets(db_session):
    """DB session with two active target pages."""
    page1 = NtaTargetPage(
        name="income_tax_rates",
        url="https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2260.htm",
        description="Income tax rate table",
        is_active=True,
    )
    page2 = NtaTargetPage(
        name="salary_deduction",
        url="https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1410.htm",
        description="Salary income deduction table",
        is_active=True,
    )
    db_session.add_all([page1, page2])
    await db_session.flush()
    return db_session


class TestCheckForChanges:
    """Tests for NtaMonitor.check_for_changes()."""

    @patch("src.infrastructure.nta_monitor.AsyncWebCrawler")
    async def test_first_crawl_stores_baseline_no_changes(self, mock_crawler_class, db_with_target):
        """First crawl should store a snapshot but report no changes."""
        mock_crawler = AsyncMock()
        mock_crawler.arun = AsyncMock(return_value=_make_crawl_result())
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_class.return_value = mock_crawler

        monitor = NtaMonitor(db_with_target, rate_limit_seconds=0)
        changes = await monitor.check_for_changes(trigger=CrawlerRunTrigger.MANUAL)

        assert changes == []

        # Verify snapshot was stored
        result = await db_with_target.execute(select(NtaPageSnapshot))
        snapshots = result.scalars().all()
        assert len(snapshots) == 1
        assert snapshots[0].status == SnapshotStatus.SUCCESS
        assert snapshots[0].raw_markdown == "# Raw content"
        assert snapshots[0].fit_markdown == "# Fit content"
        assert snapshots[0].raw_html == "<html><body>Hello</body></html>"

    @patch("src.infrastructure.nta_monitor.AsyncWebCrawler")
    async def test_second_crawl_same_content_no_changes(self, mock_crawler_class, db_with_target):
        """Second crawl with same content should report no changes."""
        mock_crawler = AsyncMock()
        mock_crawler.arun = AsyncMock(return_value=_make_crawl_result())
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_class.return_value = mock_crawler

        monitor = NtaMonitor(db_with_target, rate_limit_seconds=0)

        # First crawl
        changes1 = await monitor.check_for_changes()
        assert changes1 == []

        # Second crawl — same content
        changes2 = await monitor.check_for_changes()
        assert changes2 == []

    @patch("src.infrastructure.nta_monitor.AsyncWebCrawler")
    async def test_detects_change_when_hash_differs(self, mock_crawler_class, db_with_target):
        """Should detect a change when fit_markdown hash differs from previous."""
        call_count = 0

        async def mock_arun(url, config=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_crawl_result(fit_markdown="# Original content")
            return _make_crawl_result(fit_markdown="# Updated content")

        mock_crawler = AsyncMock()
        mock_crawler.arun = mock_arun
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_class.return_value = mock_crawler

        monitor = NtaMonitor(db_with_target, rate_limit_seconds=0)

        # First crawl — baseline
        changes1 = await monitor.check_for_changes()
        assert changes1 == []

        # Second crawl — changed content
        changes2 = await monitor.check_for_changes()
        assert len(changes2) == 1
        assert changes2[0].page_name == "income_tax_rates"
        expected_hash = hashlib.sha256("# Updated content".encode()).hexdigest()
        assert changes2[0].new_hash == expected_hash

    @patch("src.infrastructure.nta_monitor.AsyncWebCrawler")
    async def test_content_hash_is_sha256_of_fit_markdown(self, mock_crawler_class, db_with_target):
        """Verify content_hash is SHA-256 of fit_markdown."""
        fit_content = "# Tax rates 2025\n\n| Rate | Amount |\n|------|--------|\n| 5% | 100 |"
        mock_crawler = AsyncMock()
        mock_crawler.arun = AsyncMock(return_value=_make_crawl_result(fit_markdown=fit_content))
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_class.return_value = mock_crawler

        monitor = NtaMonitor(db_with_target, rate_limit_seconds=0)
        await monitor.check_for_changes()

        result = await db_with_target.execute(select(NtaPageSnapshot))
        snapshot = result.scalar_one()
        expected = hashlib.sha256(fit_content.encode()).hexdigest()
        assert snapshot.content_hash == expected

    @patch("src.infrastructure.nta_monitor.AsyncWebCrawler")
    async def test_crawl_failure_stores_failed_snapshot(self, mock_crawler_class, db_with_target):
        """Failed crawl should store a FAILED snapshot with error message."""
        mock_crawler = AsyncMock()
        mock_crawler.arun = AsyncMock(side_effect=ConnectionError("network down"))
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_class.return_value = mock_crawler

        monitor = NtaMonitor(db_with_target, rate_limit_seconds=0)
        changes = await monitor.check_for_changes()

        assert changes == []

        result = await db_with_target.execute(select(NtaPageSnapshot))
        snapshot = result.scalar_one()
        assert snapshot.status == SnapshotStatus.FAILED
        assert "network down" in snapshot.error_message

    @patch("src.infrastructure.nta_monitor.AsyncWebCrawler")
    async def test_creates_crawler_run_record(self, mock_crawler_class, db_with_target):
        """Each check_for_changes call should create a NtaCrawlerRun record."""
        mock_crawler = AsyncMock()
        mock_crawler.arun = AsyncMock(return_value=_make_crawl_result())
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_class.return_value = mock_crawler

        monitor = NtaMonitor(db_with_target, rate_limit_seconds=0)
        await monitor.check_for_changes(trigger=CrawlerRunTrigger.SCHEDULED)

        result = await db_with_target.execute(select(NtaCrawlerRun))
        run = result.scalar_one()
        assert run.trigger == CrawlerRunTrigger.SCHEDULED
        assert run.pages_checked == 1
        assert run.pages_changed == 0
        assert run.pages_failed == 0
        assert run.completed_at is not None

    @patch("src.infrastructure.nta_monitor.AsyncWebCrawler")
    async def test_run_tracks_failed_pages(self, mock_crawler_class, db_with_two_targets):
        """Crawler run should count failed pages correctly."""
        mock_crawler = AsyncMock()
        mock_crawler.arun = AsyncMock(side_effect=TimeoutError("timeout"))
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_class.return_value = mock_crawler

        monitor = NtaMonitor(db_with_two_targets, rate_limit_seconds=0)
        await monitor.check_for_changes()

        result = await db_with_two_targets.execute(select(NtaCrawlerRun))
        run = result.scalar_one()
        assert run.pages_checked == 2
        assert run.pages_failed == 2
        assert run.pages_changed == 0

    @patch("src.infrastructure.nta_monitor.AsyncWebCrawler")
    async def test_skips_inactive_pages(self, mock_crawler_class, db_session):
        """Inactive pages should not be crawled."""
        page = NtaTargetPage(
            name="inactive_page",
            url="https://example.com",
            is_active=False,
        )
        db_session.add(page)
        await db_session.flush()

        mock_crawler = AsyncMock()
        mock_crawler.arun = AsyncMock(return_value=_make_crawl_result())
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_class.return_value = mock_crawler

        monitor = NtaMonitor(db_session, rate_limit_seconds=0)
        changes = await monitor.check_for_changes()

        assert changes == []
        mock_crawler.arun.assert_not_awaited()

        result = await db_session.execute(select(NtaCrawlerRun))
        run = result.scalar_one()
        assert run.pages_checked == 0
