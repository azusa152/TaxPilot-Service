"""In-memory crawler progress tracker for real-time monitoring.

Singleton tracker that maintains the current state of all three crawler layers.
Thread-safe using asyncio.Lock. Progress data is ephemeral (not persisted to DB).
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from src.domain.enums import CrawlLayerStatus, CrawlPageStatus, CrawlerSourceType
from src.domain.schemas import CrawlerProgressResponse, LayerProgress, PageProgress
from src.logging_config import get_logger

logger = get_logger(__name__)

# Stale timeout: auto-clear progress if no updates for this duration (seconds)
STALE_TIMEOUT_SECONDS = 1800  # 30 minutes


def _reset_layer_state(layer: LayerProgress) -> None:
    """Reset a layer's mutable fields to IDLE defaults.

    Must be called while holding the layer lock.
    """
    layer.status = CrawlLayerStatus.IDLE
    layer.run_id = None
    layer.total_pages = 0
    layer.completed_pages = 0
    layer.failed_pages = 0
    layer.changed_pages = 0
    layer.progress_percent = 0.0
    layer.pages = []
    layer.started_at = None
    layer.elapsed_seconds = 0.0


class CrawlerProgressTracker:
    """Singleton in-memory tracker for crawler progress across all three layers.

    This tracker is designed to be used by the crawler infrastructure to report
    real-time progress during crawl operations. It is NOT persisted to the database.
    """

    _instance: Optional["CrawlerProgressTracker"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._layer_lock = asyncio.Lock()
        self._layers: dict[str, LayerProgress] = {
            CrawlerSourceType.NTA_TAX_ANSWER: LayerProgress(
                source_type=CrawlerSourceType.NTA_TAX_ANSWER,
                layer_label="Layer 1: NTA Tax Answer",
                status=CrawlLayerStatus.IDLE,
            ),
            CrawlerSourceType.MOF_TAX_REFORM: LayerProgress(
                source_type=CrawlerSourceType.MOF_TAX_REFORM,
                layer_label="Layer 2: MOF Tax Reform",
                status=CrawlLayerStatus.IDLE,
            ),
            CrawlerSourceType.EGOV_LAW: LayerProgress(
                source_type=CrawlerSourceType.EGOV_LAW,
                layer_label="Layer 3: e-Gov Law",
                status=CrawlLayerStatus.IDLE,
            ),
        }

    @classmethod
    def get_instance(cls) -> "CrawlerProgressTracker":
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start_layer(
        self, source_type: str, run_id: int, page_names: list[tuple[str, str]]
    ) -> None:
        """Start tracking a crawler layer.

        Args:
            source_type: CrawlerSourceType value (NTA_TAX_ANSWER / MOF_TAX_REFORM / EGOV_LAW)
            run_id: Database ID of the crawler run
            page_names: List of (page_name, page_url) tuples for all pages to crawl
        """
        async with self._layer_lock:
            if source_type not in self._layers:
                logger.warning(f"Unknown source_type: {source_type}")
                return

            layer = self._layers[source_type]
            layer.status = CrawlLayerStatus.RUNNING
            layer.run_id = run_id
            layer.total_pages = len(page_names)
            layer.completed_pages = 0
            layer.failed_pages = 0
            layer.changed_pages = 0
            layer.progress_percent = 0.0
            layer.started_at = datetime.now(timezone.utc)
            layer.elapsed_seconds = 0.0
            layer.pages = [
                PageProgress(
                    page_name=name, page_url=url, status=CrawlPageStatus.PENDING
                )
                for name, url in page_names
            ]

            logger.info(
                f"Started tracking {source_type}: run_id={run_id}, pages={len(page_names)}"
            )

    async def update_page(
        self,
        source_type: str,
        page_name: str,
        status: CrawlPageStatus,
        response_time_ms: int | None = None,
        error_message: str | None = None,
        changed: bool = False,
    ) -> None:
        """Update the status of a single page.

        Args:
            source_type: CrawlerSourceType value
            page_name: Name of the page to update
            status: New status (PENDING / CRAWLING / SUCCESS / FAILED)
            response_time_ms: Response time in milliseconds (optional)
            error_message: Error message if failed (optional)
            changed: Whether content changed (for SUCCESS status)
        """
        async with self._layer_lock:
            if source_type not in self._layers:
                return

            layer = self._layers[source_type]

            # Find and update the page
            for page in layer.pages:
                if page.page_name == page_name:
                    page.status = status
                    if response_time_ms is not None:
                        page.response_time_ms = response_time_ms
                    if error_message is not None:
                        page.error_message = error_message
                    break

            # Recalculate layer metrics
            layer.completed_pages = sum(
                1
                for p in layer.pages
                if p.status in (CrawlPageStatus.SUCCESS, CrawlPageStatus.FAILED)
            )
            layer.failed_pages = sum(
                1 for p in layer.pages if p.status == CrawlPageStatus.FAILED
            )
            if changed:
                layer.changed_pages += 1

            if layer.total_pages > 0:
                layer.progress_percent = (
                    layer.completed_pages / layer.total_pages
                ) * 100.0

            # Update elapsed time
            if layer.started_at:
                layer.elapsed_seconds = (
                    datetime.now(timezone.utc) - layer.started_at
                ).total_seconds()

    async def complete_layer(self, source_type: str) -> None:
        """Mark a layer as completed.

        Args:
            source_type: CrawlerSourceType value
        """
        async with self._layer_lock:
            if source_type not in self._layers:
                return

            layer = self._layers[source_type]
            layer.status = CrawlLayerStatus.COMPLETED
            layer.progress_percent = 100.0

            if layer.started_at:
                layer.elapsed_seconds = (
                    datetime.now(timezone.utc) - layer.started_at
                ).total_seconds()

            logger.info(
                f"Completed {source_type}: run_id={layer.run_id}, "
                f"completed={layer.completed_pages}/{layer.total_pages}, "
                f"failed={layer.failed_pages}, changed={layer.changed_pages}"
            )

    async def fail_layer(self, source_type: str, error_message: str) -> None:
        """Mark a layer as failed.

        Args:
            source_type: CrawlerSourceType value
            error_message: Error message describing the failure
        """
        async with self._layer_lock:
            if source_type not in self._layers:
                return

            layer = self._layers[source_type]
            layer.status = CrawlLayerStatus.FAILED

            if layer.started_at:
                layer.elapsed_seconds = (
                    datetime.now(timezone.utc) - layer.started_at
                ).total_seconds()

            logger.error(f"Failed {source_type}: {error_message}")

    async def get_progress(self) -> CrawlerProgressResponse:
        """Get the current progress state for all layers.

        Returns:
            CrawlerProgressResponse with all layer states.
        """
        async with self._layer_lock:
            # Auto-clear stale progress
            await self._clear_stale_progress()

            any_running = any(
                layer.status == CrawlLayerStatus.RUNNING
                for layer in self._layers.values()
            )

            return CrawlerProgressResponse(
                layers=list(self._layers.values()), any_running=any_running
            )

    async def _clear_stale_progress(self) -> None:
        """Clear stale progress data for layers that have been running too long.

        Must be called while holding ``_layer_lock``.
        """
        now = datetime.now(timezone.utc)
        for source_type, layer in self._layers.items():
            if layer.status == CrawlLayerStatus.RUNNING and layer.started_at:
                elapsed = (now - layer.started_at).total_seconds()
                if elapsed > STALE_TIMEOUT_SECONDS:
                    logger.warning(
                        f"Clearing stale progress for {source_type} (elapsed={elapsed}s)"
                    )
                    _reset_layer_state(layer)

    async def reset_layer(self, source_type: str) -> None:
        """Reset a layer to IDLE state.

        Args:
            source_type: CrawlerSourceType value
        """
        async with self._layer_lock:
            if source_type not in self._layers:
                return

            _reset_layer_state(self._layers[source_type])
            logger.info(f"Reset {source_type} to IDLE")


# Global singleton instance
_tracker = CrawlerProgressTracker.get_instance()


def get_progress_tracker() -> CrawlerProgressTracker:
    """Get the global progress tracker instance."""
    return _tracker
