"""Tests for application/nta_service.py — NTA crawler service layer."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.application.nta_service import (
    get_health_status,
    get_snapshot_detail,
    get_snapshot_markdown,
    list_crawler_runs,
    list_snapshots,
    list_target_pages,
    upsert_target_page,
)
from src.domain.enums import CrawlerRunTrigger, SnapshotStatus
from src.domain.exceptions import NotFoundError
from src.domain.schemas import NtaTargetPageConfig
from src.infrastructure.models import NtaCrawlerRun, NtaPageSnapshot, NtaTargetPage


@pytest.fixture()
async def db_with_pages(db_session):
    """DB session with target pages and snapshots."""
    page = NtaTargetPage(
        name="income_tax_rates",
        url="https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2260.htm",
        description="Income tax rate table",
        is_active=True,
    )
    db_session.add(page)
    await db_session.flush()

    snapshot = NtaPageSnapshot(
        target_page_id=page.id,
        content_hash="abc123def456",
        raw_markdown="# Raw content",
        fit_markdown="# Fit content",
        status=SnapshotStatus.SUCCESS,
        response_time_ms=500,
    )
    db_session.add(snapshot)
    await db_session.flush()

    return db_session


class TestUpsertTargetPage:
    """Tests for upsert_target_page()."""

    async def test_creates_new_target_page(self, db_session):
        config = NtaTargetPageConfig(
            name="income_tax_rates",
            url="https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2260.htm",
            description="Income tax rate table",
            check_interval_hours=12,
        )

        result = await upsert_target_page(db_session, config)

        assert result.name == "income_tax_rates"
        assert result.url == "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2260.htm"
        assert result.description == "Income tax rate table"
        assert result.check_interval_hours == 12
        assert result.is_active is True

    async def test_updates_existing_target_page(self, db_session):
        # Create initial page
        page = NtaTargetPage(
            name="income_tax_rates",
            url="https://old-url.com",
            is_active=True,
        )
        db_session.add(page)
        await db_session.flush()

        # Update via upsert
        config = NtaTargetPageConfig(
            name="income_tax_rates",
            url="https://new-url.com",
            description="Updated description",
            is_active=False,
            check_interval_hours=48,
        )
        result = await upsert_target_page(db_session, config)

        assert result.url == "https://new-url.com"
        assert result.description == "Updated description"
        assert result.is_active is False
        assert result.check_interval_hours == 48

        # Verify only one page exists
        all_pages = await db_session.execute(select(NtaTargetPage))
        assert len(all_pages.scalars().all()) == 1


class TestListTargetPages:
    """Tests for list_target_pages()."""

    async def test_returns_empty_list(self, db_session):
        result = await list_target_pages(db_session)
        assert result == []

    async def test_returns_all_pages_sorted(self, db_session):
        db_session.add_all([
            NtaTargetPage(name="salary_deduction", url="https://b.com", is_active=True),
            NtaTargetPage(name="income_tax_rates", url="https://a.com", is_active=True),
        ])
        await db_session.flush()

        result = await list_target_pages(db_session)
        assert len(result) == 2
        assert result[0].name == "income_tax_rates"
        assert result[1].name == "salary_deduction"


class TestGetHealthStatus:
    """Tests for get_health_status()."""

    async def test_degraded_when_no_runs(self, db_session):
        result = await get_health_status(db_session)
        assert result.status == "degraded"
        assert result.last_run is None
        assert result.total_target_pages == 0
        assert result.active_target_pages == 0

    async def test_healthy_when_last_run_no_failures(self, db_session):
        page = NtaTargetPage(name="test", url="https://example.com", is_active=True)
        db_session.add(page)

        run = NtaCrawlerRun(
            trigger=CrawlerRunTrigger.MANUAL,
            pages_checked=1,
            pages_changed=0,
            pages_failed=0,
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        await db_session.flush()

        result = await get_health_status(db_session)
        assert result.status == "healthy"
        assert result.last_run is not None
        assert result.last_run.trigger == "MANUAL"
        assert result.total_target_pages == 1
        assert result.active_target_pages == 1

    async def test_degraded_when_some_failures(self, db_session):
        run = NtaCrawlerRun(
            trigger=CrawlerRunTrigger.SCHEDULED,
            pages_checked=3,
            pages_changed=0,
            pages_failed=1,
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        await db_session.flush()

        result = await get_health_status(db_session)
        assert result.status == "degraded"

    async def test_error_when_all_pages_failed(self, db_session):
        run = NtaCrawlerRun(
            trigger=CrawlerRunTrigger.MANUAL,
            pages_checked=2,
            pages_changed=0,
            pages_failed=2,
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        await db_session.flush()

        result = await get_health_status(db_session)
        assert result.status == "error"


class TestListSnapshots:
    """Tests for list_snapshots()."""

    async def test_returns_snapshots(self, db_with_pages):
        result = await list_snapshots(db_with_pages)
        assert len(result) == 1
        assert result[0].target_page_name == "income_tax_rates"
        assert result[0].status == "SUCCESS"
        assert result[0].fit_markdown == "# Fit content"

    async def test_filter_by_page_name(self, db_with_pages):
        result = await list_snapshots(db_with_pages, page_name="nonexistent")
        assert len(result) == 0

        result = await list_snapshots(db_with_pages, page_name="income_tax_rates")
        assert len(result) == 1

    async def test_empty_when_no_snapshots(self, db_session):
        result = await list_snapshots(db_session)
        assert result == []

    async def test_changes_only_filters_to_changed_snapshots(self, db_session):
        """changes_only=True should return only snapshots where hash changed."""
        page = NtaTargetPage(
            name="income_tax_rates",
            url="https://example.com",
            is_active=True,
        )
        db_session.add(page)
        await db_session.flush()

        # Snapshot 1: baseline (hash A)
        s1 = NtaPageSnapshot(
            target_page_id=page.id,
            content_hash="hash_a",
            fit_markdown="# Version A",
            status=SnapshotStatus.SUCCESS,
        )
        db_session.add(s1)
        await db_session.flush()

        # Snapshot 2: same hash (hash A) — no change
        s2 = NtaPageSnapshot(
            target_page_id=page.id,
            content_hash="hash_a",
            fit_markdown="# Version A",
            status=SnapshotStatus.SUCCESS,
        )
        db_session.add(s2)
        await db_session.flush()

        # Snapshot 3: different hash (hash B) — change
        s3 = NtaPageSnapshot(
            target_page_id=page.id,
            content_hash="hash_b",
            fit_markdown="# Version B",
            status=SnapshotStatus.SUCCESS,
        )
        db_session.add(s3)
        await db_session.flush()

        # Without filter: all 3 snapshots
        all_snapshots = await list_snapshots(db_session)
        assert len(all_snapshots) == 3

        # With changes_only: baseline + changed snapshot (no duplicate hash A)
        changed = await list_snapshots(db_session, changes_only=True)
        assert len(changed) == 2
        hashes = [s.content_hash for s in changed]
        assert "hash_a" in hashes
        assert "hash_b" in hashes


class TestGetSnapshotDetail:
    """Tests for get_snapshot_detail()."""

    async def test_returns_snapshot(self, db_with_pages):
        # Get the snapshot ID
        snapshots = await list_snapshots(db_with_pages)
        snapshot_id = snapshots[0].id

        result = await get_snapshot_detail(db_with_pages, snapshot_id)
        assert result.target_page_name == "income_tax_rates"
        assert result.content_hash == "abc123def456"
        assert result.fit_markdown == "# Fit content"

    async def test_not_found_raises(self, db_session):
        with pytest.raises(NotFoundError, match="Snapshot 9999 not found"):
            await get_snapshot_detail(db_session, 9999)


class TestGetSnapshotMarkdown:
    """Tests for get_snapshot_markdown()."""

    async def test_returns_markdown(self, db_with_pages):
        snapshots = await list_snapshots(db_with_pages)
        snapshot_id = snapshots[0].id

        result = await get_snapshot_markdown(db_with_pages, snapshot_id)
        assert result == "# Fit content"

    async def test_not_found_raises(self, db_session):
        with pytest.raises(NotFoundError, match="Snapshot 9999 not found"):
            await get_snapshot_markdown(db_session, 9999)

    async def test_failed_snapshot_with_null_markdown_raises(self, db_session):
        """FAILED snapshot with no fit_markdown should raise a clear error."""
        page = NtaTargetPage(
            name="test_page",
            url="https://example.com",
            is_active=True,
        )
        db_session.add(page)
        await db_session.flush()

        snapshot = NtaPageSnapshot(
            target_page_id=page.id,
            content_hash="",
            fit_markdown=None,
            status=SnapshotStatus.FAILED,
            error_message="network down",
        )
        db_session.add(snapshot)
        await db_session.flush()

        with pytest.raises(NotFoundError, match="has no markdown content"):
            await get_snapshot_markdown(db_session, snapshot.id)


class TestListCrawlerRuns:
    """Tests for list_crawler_runs()."""

    async def test_returns_empty(self, db_session):
        result = await list_crawler_runs(db_session)
        assert result == []

    async def test_returns_runs_ordered_by_most_recent(self, db_session):
        run1 = NtaCrawlerRun(trigger=CrawlerRunTrigger.MANUAL, pages_checked=1, pages_changed=0, pages_failed=0)
        run2 = NtaCrawlerRun(trigger=CrawlerRunTrigger.SCHEDULED, pages_checked=2, pages_changed=1, pages_failed=0)
        db_session.add_all([run1, run2])
        await db_session.flush()

        result = await list_crawler_runs(db_session)
        assert len(result) == 2
        # Most recent first
        assert result[0].trigger == "SCHEDULED"
        assert result[1].trigger == "MANUAL"
