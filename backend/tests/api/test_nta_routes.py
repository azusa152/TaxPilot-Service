"""Integration tests for api/nta_routes.py — NTA crawler endpoints."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.domain.enums import CrawlerRunTrigger, SnapshotStatus
from src.infrastructure.models import NtaCrawlerRun, NtaPageSnapshot, NtaTargetPage


def _make_crawl_result(
    raw_markdown: str = "# Raw content",
    fit_markdown: str = "# Fit content",
    html: str = "<html>test</html>",
):
    markdown = SimpleNamespace(raw_markdown=raw_markdown, fit_markdown=fit_markdown)
    return SimpleNamespace(markdown=markdown, html=html)


class TestPutTarget:
    """Tests for PUT /admin/nta/targets."""

    async def test_creates_target_page(self, client, db_session):
        response = await client.put(
            "/admin/nta/targets",
            json={
                "name": "income_tax_rates",
                "url": "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2260.htm",
                "description": "Income tax rate table",
                "check_interval_hours": 24,
                "is_active": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "income_tax_rates"
        assert data["is_active"] is True

    async def test_updates_existing_target(self, client, db_session):
        # Create
        await client.put(
            "/admin/nta/targets",
            json={
                "name": "test_page",
                "url": "https://old-url.com",
            },
        )

        # Update
        response = await client.put(
            "/admin/nta/targets",
            json={
                "name": "test_page",
                "url": "https://new-url.com",
                "is_active": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "https://new-url.com"
        assert data["is_active"] is False


class TestGetTargets:
    """Tests for GET /admin/nta/targets."""

    async def test_returns_empty_list(self, client):
        response = await client.get("/admin/nta/targets")
        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_created_targets(self, client, db_session):
        # Create a target page via API
        await client.put(
            "/admin/nta/targets",
            json={"name": "test_page", "url": "https://example.com"},
        )

        response = await client.get("/admin/nta/targets")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "test_page"


class TestGetHealth:
    """Tests for GET /admin/nta/health."""

    async def test_returns_health_status(self, client):
        response = await client.get("/admin/nta/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded", "error")
        assert "total_target_pages" in data
        assert "active_target_pages" in data


class TestPostCheckNow:
    """Tests for POST /admin/nta/check-now."""

    @patch("src.infrastructure.nta_monitor.AsyncWebCrawler")
    async def test_triggers_crawl_returns_changes(self, mock_crawler_class, client, db_session):
        # Create a target page first
        page = NtaTargetPage(
            name="income_tax_rates",
            url="https://www.nta.go.jp/test",
            is_active=True,
        )
        db_session.add(page)
        await db_session.flush()

        mock_crawler = AsyncMock()
        mock_crawler.arun = AsyncMock(return_value=_make_crawl_result())
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_class.return_value = mock_crawler

        response = await client.post("/admin/nta/check-now")
        assert response.status_code == 200
        data = response.json()
        # First run = no changes
        assert isinstance(data, list)
        assert len(data) == 0


class TestGetSnapshots:
    """Tests for GET /admin/nta/snapshots and /admin/nta/snapshots/{id}."""

    async def test_returns_empty_list(self, client):
        response = await client.get("/admin/nta/snapshots")
        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_snapshot_detail(self, client, db_session):
        page = NtaTargetPage(
            name="income_tax_rates",
            url="https://www.nta.go.jp/test",
            is_active=True,
        )
        db_session.add(page)
        await db_session.flush()

        snapshot = NtaPageSnapshot(
            target_page_id=page.id,
            content_hash="abc123",
            fit_markdown="# Test content",
            raw_markdown="# Raw test",
            status=SnapshotStatus.SUCCESS,
            response_time_ms=200,
        )
        db_session.add(snapshot)
        await db_session.flush()

        response = await client.get(f"/admin/nta/snapshots/{snapshot.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["target_page_name"] == "income_tax_rates"
        assert data["content_hash"] == "abc123"
        assert data["fit_markdown"] == "# Test content"

    async def test_snapshot_markdown_endpoint(self, client, db_session):
        page = NtaTargetPage(
            name="test_page",
            url="https://example.com",
            is_active=True,
        )
        db_session.add(page)
        await db_session.flush()

        snapshot = NtaPageSnapshot(
            target_page_id=page.id,
            content_hash="def456",
            fit_markdown="# Markdown for LLM",
            status=SnapshotStatus.SUCCESS,
        )
        db_session.add(snapshot)
        await db_session.flush()

        response = await client.get(f"/admin/nta/snapshots/{snapshot.id}/markdown")
        assert response.status_code == 200
        data = response.json()
        assert data["fit_markdown"] == "# Markdown for LLM"


class TestGetRuns:
    """Tests for GET /admin/nta/runs."""

    async def test_returns_empty_list(self, client):
        response = await client.get("/admin/nta/runs")
        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_run_history(self, client, db_session):
        run = NtaCrawlerRun(
            trigger=CrawlerRunTrigger.MANUAL,
            pages_checked=2,
            pages_changed=1,
            pages_failed=0,
        )
        db_session.add(run)
        await db_session.flush()

        response = await client.get("/admin/nta/runs")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["trigger"] == "MANUAL"
        assert data[0]["pages_checked"] == 2
        assert data[0]["pages_changed"] == 1
