"""Tests for the CrawlerProgressTracker in-memory singleton."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.domain.enums import CrawlLayerStatus, CrawlPageStatus, CrawlerSourceType
from src.infrastructure.crawler_progress import (
    STALE_TIMEOUT_SECONDS,
    CrawlerProgressTracker,
    get_progress_tracker,
)


@pytest.fixture
async def tracker():
    """Get a fresh tracker instance for each test."""
    tracker = CrawlerProgressTracker.get_instance()
    # Reset all layers to IDLE before each test
    await tracker.reset_layer(CrawlerSourceType.NTA_TAX_ANSWER)
    await tracker.reset_layer(CrawlerSourceType.MOF_TAX_REFORM)
    await tracker.reset_layer(CrawlerSourceType.EGOV_LAW)
    return tracker


@pytest.mark.asyncio
async def test_tracker_singleton():
    """Test that get_progress_tracker returns the same instance."""
    tracker1 = get_progress_tracker()
    tracker2 = get_progress_tracker()
    tracker3 = CrawlerProgressTracker.get_instance()

    assert tracker1 is tracker2
    assert tracker2 is tracker3


@pytest.mark.asyncio
async def test_start_layer(tracker):
    """Test starting a layer initializes progress correctly."""
    pages = [
        ("income_tax_rates", "https://example.com/1"),
        ("deduction_rules", "https://example.com/2"),
    ]

    await tracker.start_layer(CrawlerSourceType.NTA_TAX_ANSWER, run_id=123, page_names=pages)

    progress = await tracker.get_progress()
    nta_layer = next(
        layer for layer in progress.layers if layer.source_type == CrawlerSourceType.NTA_TAX_ANSWER
    )

    assert nta_layer.status == CrawlLayerStatus.RUNNING
    assert nta_layer.run_id == 123
    assert nta_layer.total_pages == 2
    assert nta_layer.completed_pages == 0
    assert nta_layer.failed_pages == 0
    assert nta_layer.changed_pages == 0
    assert nta_layer.progress_percent == 0.0
    assert len(nta_layer.pages) == 2
    assert all(page.status == CrawlPageStatus.PENDING for page in nta_layer.pages)
    assert nta_layer.started_at is not None


@pytest.mark.asyncio
async def test_update_page_status(tracker):
    """Test updating individual page status."""
    pages = [("page1", "https://example.com/1")]
    await tracker.start_layer(CrawlerSourceType.NTA_TAX_ANSWER, run_id=1, page_names=pages)

    # Mark as CRAWLING
    await tracker.update_page(CrawlerSourceType.NTA_TAX_ANSWER, "page1", CrawlPageStatus.CRAWLING)

    progress = await tracker.get_progress()
    nta_layer = next(
        layer for layer in progress.layers if layer.source_type == CrawlerSourceType.NTA_TAX_ANSWER
    )
    assert nta_layer.pages[0].status == CrawlPageStatus.CRAWLING

    # Mark as SUCCESS with response time
    await tracker.update_page(
        CrawlerSourceType.NTA_TAX_ANSWER,
        "page1",
        CrawlPageStatus.SUCCESS,
        response_time_ms=250,
        changed=True,
    )

    progress = await tracker.get_progress()
    nta_layer = next(
        layer for layer in progress.layers if layer.source_type == CrawlerSourceType.NTA_TAX_ANSWER
    )
    assert nta_layer.pages[0].status == CrawlPageStatus.SUCCESS
    assert nta_layer.pages[0].response_time_ms == 250
    assert nta_layer.completed_pages == 1
    assert nta_layer.changed_pages == 1
    assert nta_layer.progress_percent == 100.0


@pytest.mark.asyncio
async def test_update_page_with_error(tracker):
    """Test updating page status with error message."""
    pages = [("page1", "https://example.com/1")]
    await tracker.start_layer(CrawlerSourceType.MOF_TAX_REFORM, run_id=2, page_names=pages)

    await tracker.update_page(
        CrawlerSourceType.MOF_TAX_REFORM,
        "page1",
        CrawlPageStatus.FAILED,
        error_message="Connection timeout",
    )

    progress = await tracker.get_progress()
    mof_layer = next(
        layer for layer in progress.layers if layer.source_type == CrawlerSourceType.MOF_TAX_REFORM
    )
    assert mof_layer.pages[0].status == CrawlPageStatus.FAILED
    assert mof_layer.pages[0].error_message == "Connection timeout"
    assert mof_layer.failed_pages == 1
    assert mof_layer.completed_pages == 1


@pytest.mark.asyncio
async def test_complete_layer(tracker):
    """Test completing a layer sets status to COMPLETED."""
    pages = [("page1", "https://example.com/1")]
    await tracker.start_layer(CrawlerSourceType.EGOV_LAW, run_id=3, page_names=pages)

    await tracker.update_page(
        CrawlerSourceType.EGOV_LAW, "page1", CrawlPageStatus.SUCCESS, response_time_ms=100
    )
    await tracker.complete_layer(CrawlerSourceType.EGOV_LAW)

    progress = await tracker.get_progress()
    egov_layer = next(
        layer for layer in progress.layers if layer.source_type == CrawlerSourceType.EGOV_LAW
    )
    assert egov_layer.status == CrawlLayerStatus.COMPLETED
    assert egov_layer.progress_percent == 100.0


@pytest.mark.asyncio
async def test_fail_layer(tracker):
    """Test failing a layer sets status to FAILED."""
    pages = [("page1", "https://example.com/1")]
    await tracker.start_layer(CrawlerSourceType.NTA_TAX_ANSWER, run_id=4, page_names=pages)

    await tracker.fail_layer(CrawlerSourceType.NTA_TAX_ANSWER, "Network error")

    progress = await tracker.get_progress()
    nta_layer = next(
        layer for layer in progress.layers if layer.source_type == CrawlerSourceType.NTA_TAX_ANSWER
    )
    assert nta_layer.status == CrawlLayerStatus.FAILED


@pytest.mark.asyncio
async def test_any_running_flag(tracker):
    """Test that any_running flag reflects current state."""
    # Initially all IDLE
    progress = await tracker.get_progress()
    assert progress.any_running is False

    # Start one layer
    pages = [("page1", "https://example.com/1")]
    await tracker.start_layer(CrawlerSourceType.NTA_TAX_ANSWER, run_id=5, page_names=pages)

    progress = await tracker.get_progress()
    assert progress.any_running is True

    # Complete the layer
    await tracker.complete_layer(CrawlerSourceType.NTA_TAX_ANSWER)

    progress = await tracker.get_progress()
    assert progress.any_running is False


@pytest.mark.asyncio
async def test_multiple_layers_running(tracker):
    """Test tracking multiple layers simultaneously."""
    pages1 = [("nta_page", "https://example.com/nta")]
    pages2 = [("mof_page", "https://example.com/mof")]

    await tracker.start_layer(CrawlerSourceType.NTA_TAX_ANSWER, run_id=6, page_names=pages1)
    await tracker.start_layer(CrawlerSourceType.MOF_TAX_REFORM, run_id=7, page_names=pages2)

    progress = await tracker.get_progress()

    nta_layer = next(
        layer for layer in progress.layers if layer.source_type == CrawlerSourceType.NTA_TAX_ANSWER
    )
    mof_layer = next(
        layer for layer in progress.layers if layer.source_type == CrawlerSourceType.MOF_TAX_REFORM
    )

    assert nta_layer.status == CrawlLayerStatus.RUNNING
    assert mof_layer.status == CrawlLayerStatus.RUNNING
    assert progress.any_running is True


@pytest.mark.asyncio
async def test_reset_layer(tracker):
    """Test resetting a layer clears its state."""
    pages = [("page1", "https://example.com/1")]
    await tracker.start_layer(CrawlerSourceType.NTA_TAX_ANSWER, run_id=8, page_names=pages)

    await tracker.reset_layer(CrawlerSourceType.NTA_TAX_ANSWER)

    progress = await tracker.get_progress()
    nta_layer = next(
        layer for layer in progress.layers if layer.source_type == CrawlerSourceType.NTA_TAX_ANSWER
    )

    assert nta_layer.status == CrawlLayerStatus.IDLE
    assert nta_layer.run_id is None
    assert nta_layer.total_pages == 0
    assert nta_layer.completed_pages == 0
    assert nta_layer.pages == []


@pytest.mark.asyncio
async def test_elapsed_time_updates(tracker):
    """Test that elapsed_seconds is updated correctly."""
    pages = [("page1", "https://example.com/1")]
    await tracker.start_layer(CrawlerSourceType.NTA_TAX_ANSWER, run_id=9, page_names=pages)

    # Small delay to let time pass
    await asyncio.sleep(0.1)

    await tracker.update_page(
        CrawlerSourceType.NTA_TAX_ANSWER, "page1", CrawlPageStatus.SUCCESS, response_time_ms=50
    )

    progress = await tracker.get_progress()
    nta_layer = next(
        layer for layer in progress.layers if layer.source_type == CrawlerSourceType.NTA_TAX_ANSWER
    )

    # Elapsed time should be > 0 after the sleep
    assert nta_layer.elapsed_seconds > 0.0


@pytest.mark.asyncio
async def test_stale_progress_cleanup(tracker):
    """Test that stale progress is auto-cleared after timeout."""
    pages = [("page1", "https://example.com/1")]
    await tracker.start_layer(CrawlerSourceType.NTA_TAX_ANSWER, run_id=10, page_names=pages)

    # Manually set started_at to a time beyond stale timeout
    async with tracker._layer_lock:
        layer = tracker._layers[CrawlerSourceType.NTA_TAX_ANSWER]
        layer.started_at = datetime.now(timezone.utc) - timedelta(seconds=STALE_TIMEOUT_SECONDS + 10)

    # Trigger cleanup by calling get_progress
    progress = await tracker.get_progress()
    nta_layer = next(
        layer for layer in progress.layers if layer.source_type == CrawlerSourceType.NTA_TAX_ANSWER
    )

    # Layer should be reset to IDLE due to staleness
    assert nta_layer.status == CrawlLayerStatus.IDLE
    assert nta_layer.run_id is None


@pytest.mark.asyncio
async def test_progress_percent_calculation(tracker):
    """Test that progress_percent is calculated correctly."""
    pages = [
        ("page1", "https://example.com/1"),
        ("page2", "https://example.com/2"),
        ("page3", "https://example.com/3"),
        ("page4", "https://example.com/4"),
    ]
    await tracker.start_layer(CrawlerSourceType.NTA_TAX_ANSWER, run_id=11, page_names=pages)

    # Complete 2 out of 4 pages
    await tracker.update_page(
        CrawlerSourceType.NTA_TAX_ANSWER, "page1", CrawlPageStatus.SUCCESS, response_time_ms=100
    )
    await tracker.update_page(
        CrawlerSourceType.NTA_TAX_ANSWER, "page2", CrawlPageStatus.FAILED, error_message="Error"
    )

    progress = await tracker.get_progress()
    nta_layer = next(
        layer for layer in progress.layers if layer.source_type == CrawlerSourceType.NTA_TAX_ANSWER
    )

    # 2 completed out of 4 = 50%
    assert nta_layer.progress_percent == pytest.approx(50.0)
    assert nta_layer.completed_pages == 2
    assert nta_layer.failed_pages == 1


@pytest.mark.asyncio
async def test_unknown_layer_handling(tracker):
    """Test that operations on unknown layers are handled gracefully."""
    # Should not raise an error
    await tracker.start_layer("UNKNOWN_LAYER", run_id=999, page_names=[("test", "url")])
    await tracker.update_page("UNKNOWN_LAYER", "test", CrawlPageStatus.SUCCESS)
    await tracker.complete_layer("UNKNOWN_LAYER")
    await tracker.fail_layer("UNKNOWN_LAYER", "error")
    await tracker.reset_layer("UNKNOWN_LAYER")

    # Progress should still be valid
    progress = await tracker.get_progress()
    assert len(progress.layers) == 3  # Only the 3 known layers
