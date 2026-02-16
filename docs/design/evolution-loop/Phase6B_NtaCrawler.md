# Phase 6B: NTA Crawler

**Goal:** Upgrade the NTA monitor from an in-memory skeleton to a persistent, schedulable crawler using **Crawl4AI** for LLM-optimized markdown extraction. Store parsed markdown in the database so reviewers can use it with other LLMs for independent analysis.

**Depends on:** Phase 2 (DB models); does NOT depend on Phase 6A
**Produces:** Persistent hash storage, LLM-ready markdown via Crawl4AI, `NtaPageSnapshot` table with stored markdown, configurable target pages, admin crawler monitor dashboard

---

## Context

The current `nta_monitor.py` is a skeleton that uses `httpx` and `BeautifulSoup` for basic HTML fetching. It lacks:
- Persistent storage (hash comparison is in-memory)
- LLM-optimized output (raw HTML is not ideal for LLM parsing)
- Table preservation (NTA tax bracket tables are critical)
- Admin visibility (no monitoring dashboard)
- Configurable target pages

**Crawl4AI** (v0.7.8+, MIT license) is an open-source async web crawler optimized for AI/LLM workflows. Since our crawled NTA content goes directly to LLMs for parsing, Crawl4AI provides purpose-built features:

| Feature | Benefit |
|---------|---------|
| `raw_markdown` | Full HTML-to-Markdown conversion preserving tables, headings, lists |
| `fit_markdown` | LLM-optimized version that strips navigation, sidebars, boilerplate via `PruningContentFilter` |
| Async-native | `AsyncWebCrawler` integrates naturally with FastAPI's async stack |
| Table preservation | Critical for NTA tax rate bracket tables |
| No JS rendering | NTA pages are static HTML — no headless browser overhead |

**Stored markdown as a reusable asset:**

Both `raw_markdown` and `fit_markdown` are stored in `NtaPageSnapshot`. This enables:
1. The Evolution Loop pipeline to parse changes via LLM (Phase 6C)
2. Admin reviewers to copy the markdown and paste into their own LLM for independent verification
3. Historical comparison — markdown diffs are human-readable unlike raw HTML diffs
4. Future re-processing — if LLM prompts improve, snapshots can be re-parsed without re-crawling

---

## Tasks

### Task 6B.1: Dependencies

**File:** `backend/pyproject.toml`

```toml
[project]
dependencies = [
    # ... existing deps ...
    "crawl4ai>=0.7.8",
]
```

Note: `crawl4ai` replaces `beautifulsoup4` and `httpx` for this feature (though those may remain for other uses).

### Task 6B.2: Enums

**File:** `backend/src/domain/enums.py`

```python
class CrawlerRunTrigger(str, Enum):
    """How a crawler run was triggered."""
    MANUAL = "MANUAL"
    SCHEDULED = "SCHEDULED"


class SnapshotStatus(str, Enum):
    """Status of an individual page snapshot."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
```

### Task 6B.3: Database Models

**File:** `backend/src/infrastructure/models.py`

Add three new tables:

```python
class NtaTargetPage(Base):
    """Configurable list of NTA pages to monitor."""
    __tablename__ = "nta_target_pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    check_interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    snapshots: Mapped[list["NtaPageSnapshot"]] = relationship(
        back_populates="target_page", order_by="desc(NtaPageSnapshot.fetched_at)"
    )


class NtaPageSnapshot(Base):
    """Stores a point-in-time snapshot of an NTA page.

    NOTE: Crawl4AI CrawlResult attribute names may vary by version.
    Verify the actual attribute names (`html`, `markdown`, `fit_markdown`, etc.)
    against the installed crawl4ai version at implementation time.
    See: https://docs.crawl4ai.com/api/crawl-result/
    """
    __tablename__ = "nta_page_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_page_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("nta_target_pages.id"), nullable=False
    )
    crawler_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("nta_crawler_runs.id"), nullable=True
    )
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # SHA-256 of fit_markdown
    raw_html: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Original HTML for audit
    raw_markdown: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Full markdown conversion
    fit_markdown: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # LLM-optimized markdown (boilerplate removed)
    extracted_tables: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # Structured table data for programmatic access
    status: Mapped[str] = mapped_column(
        String(20), default="SUCCESS"
    )  # SUCCESS / FAILED / TIMEOUT
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    target_page: Mapped["NtaTargetPage"] = relationship(back_populates="snapshots")

    __table_args__ = (
        Index("ix_nta_snapshots_target_fetched", "target_page_id", "fetched_at"),
        Index("ix_nta_snapshots_content_hash", "content_hash"),
    )


class NtaCrawlerRun(Base):
    """Records each crawler run (manual or scheduled)."""
    __tablename__ = "nta_crawler_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trigger: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # MANUAL / SCHEDULED
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pages_checked: Mapped[int] = mapped_column(Integer, default=0)
    pages_changed: Mapped[int] = mapped_column(Integer, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index("ix_nta_crawler_runs_started_at", "started_at"),
    )
```

### Task 6B.4: Pydantic Schemas

**File:** `backend/src/domain/schemas.py`

```python
class NtaTargetPageConfig(BaseModel):
    """Schema for creating/updating a target NTA page."""
    name: str = Field(description="Short name for the page (e.g., 'income_tax_rates')")
    url: str = Field(description="Full URL of the NTA page")
    description: str | None = Field(
        None, description="Description of what this page contains"
    )
    is_active: bool = Field(default=True, description="Whether to actively monitor this page")
    check_interval_hours: int = Field(
        default=24, description="How often to check this page (in hours)"
    )


class NtaPageChange(BaseModel):
    """Represents a detected change on an NTA page."""
    page_name: str = Field(description="Name of the NTA target page")
    page_url: str = Field(description="URL of the NTA page")
    previous_hash: str | None = Field(description="Content hash of the previous snapshot")
    new_hash: str = Field(description="Content hash of the new snapshot")
    snapshot_id: int = Field(description="ID of the new snapshot")


class NtaSnapshotDetail(BaseModel):
    """Detailed view of a single snapshot including markdown content."""
    id: int = Field(description="Snapshot ID")
    target_page_name: str = Field(description="Name of the monitored page")
    target_page_url: str = Field(description="URL of the monitored page")
    content_hash: str = Field(description="SHA-256 hash of fit_markdown")
    raw_markdown: str | None = Field(description="Full page as markdown")
    fit_markdown: str | None = Field(description="LLM-optimized markdown (boilerplate removed)")
    extracted_tables: dict | None = Field(description="Structured table data as JSON")
    status: str = Field(description="SUCCESS / FAILED / TIMEOUT")
    error_message: str | None = Field(description="Error message if status is FAILED/TIMEOUT")
    response_time_ms: int | None = Field(description="Response time in milliseconds")
    fetched_at: datetime

    model_config = {"from_attributes": True}


class CrawlerRunSummary(BaseModel):
    """Summary of a single crawler run."""
    id: int = Field(description="Run ID")
    trigger: str = Field(description="MANUAL or SCHEDULED")
    started_at: datetime
    completed_at: datetime | None
    pages_checked: int
    pages_changed: int
    pages_failed: int

    model_config = {"from_attributes": True}


class CrawlerHealthStatus(BaseModel):
    """Overall health status of the crawler."""
    status: str = Field(
        description="Health indicator: 'healthy' (green), 'degraded' (yellow), 'error' (red)"
    )
    last_run: CrawlerRunSummary | None = Field(description="Most recent crawler run")
    next_scheduled_run: datetime | None = Field(description="Next scheduled crawl time")
    total_target_pages: int = Field(description="Total number of monitored pages")
    active_target_pages: int = Field(description="Number of actively monitored pages")
```

### Task 6B.5: NTA Monitor (Infrastructure Layer)

**File:** `backend/src/infrastructure/nta_monitor.py`

Refactor from skeleton to Crawl4AI-based implementation:

```python
import hashlib
import asyncio
from datetime import datetime, timezone

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.schemas import NtaPageChange
from src.infrastructure.models import NtaTargetPage, NtaPageSnapshot, NtaCrawlerRun
from src.logging_config import get_logger

logger = get_logger(__name__)

# Crawl4AI configuration for NTA pages
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

    def __init__(self, db: AsyncSession, rate_limit_seconds: float = 2.0):
        self.db = db
        self.rate_limit_seconds = rate_limit_seconds

    async def check_for_changes(
        self, trigger: str = "MANUAL"
    ) -> list[NtaPageChange]:
        """Crawl all active target pages and detect changes.

        Args:
            trigger: How this check was triggered ("MANUAL" or "SCHEDULED")

        Returns:
            List of NtaPageChange objects for pages where content changed.
        """
        # Create a crawler run record
        run = NtaCrawlerRun(trigger=trigger)
        self.db.add(run)
        await self.db.flush()

        # Get all active target pages
        result = await self.db.execute(
            select(NtaTargetPage).where(NtaTargetPage.is_active == True)
        )
        target_pages = result.scalars().all()

        changes: list[NtaPageChange] = []

        async with AsyncWebCrawler() as crawler:
            for page in target_pages:
                try:
                    change = await self._check_page(crawler, page, run.id)
                    run.pages_checked += 1
                    if change:
                        changes.append(change)
                        run.pages_changed += 1
                except Exception as e:
                    logger.error(f"Failed to crawl {page.name}: {e}")
                    run.pages_checked += 1
                    run.pages_failed += 1
                    # Store a FAILED snapshot
                    snapshot = NtaPageSnapshot(
                        target_page_id=page.id,
                        crawler_run_id=run.id,
                        content_hash="",
                        status="FAILED",
                        error_message=str(e),
                    )
                    self.db.add(snapshot)

                # Rate limiting between pages
                await asyncio.sleep(self.rate_limit_seconds)

        run.completed_at = datetime.now(timezone.utc)
        await self.db.flush()

        logger.info(
            f"Crawler run complete: checked={run.pages_checked}, "
            f"changed={run.pages_changed}, failed={run.pages_failed}"
        )
        return changes

    async def _check_page(
        self,
        crawler: AsyncWebCrawler,
        page: NtaTargetPage,
        run_id: int,
    ) -> NtaPageChange | None:
        """Crawl a single page and check for changes.

        Returns NtaPageChange if content has changed, None otherwise.
        """
        import time

        start = time.time()
        result = await crawler.arun(page.url, config=CRAWL_CONFIG)
        response_time_ms = int((time.time() - start) * 1000)

        raw_md = result.markdown.raw_markdown
        fit_md = result.markdown.fit_markdown
        content_hash = hashlib.sha256(fit_md.encode()).hexdigest()

        # Get previous snapshot hash
        prev_result = await self.db.execute(
            select(NtaPageSnapshot)
            .where(
                NtaPageSnapshot.target_page_id == page.id,
                NtaPageSnapshot.status == "SUCCESS",
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
            raw_html=result.html,  # CrawlResult.html — verify attribute name against installed Crawl4AI version
            raw_markdown=raw_md,
            fit_markdown=fit_md,
            status="SUCCESS",
            response_time_ms=response_time_ms,
        )
        self.db.add(snapshot)
        await self.db.flush()

        # Check for change
        if prev_hash and prev_hash != content_hash:
            logger.info(f"Change detected on {page.name}: {prev_hash[:8]}→{content_hash[:8]}")
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
```

### Task 6B.6: NTA Service (Application Layer)

**File:** `backend/src/application/nta_service.py`

Service layer for triggering crawls, querying history, managing target pages, and health status.

```python
from sqlalchemy import select, func as sqla_func
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.schemas import (
    CrawlerHealthStatus,
    CrawlerRunSummary,
    NtaPageChange,
    NtaSnapshotDetail,
    NtaTargetPageConfig,
)
from src.infrastructure.models import NtaCrawlerRun, NtaPageSnapshot, NtaTargetPage
from src.infrastructure.nta_monitor import NtaMonitor
from src.logging_config import get_logger

logger = get_logger(__name__)


async def trigger_crawl(
    db: AsyncSession, trigger: str = "MANUAL"
) -> list[NtaPageChange]:
    """Trigger a crawler run and return detected changes."""
    monitor = NtaMonitor(db)
    return await monitor.check_for_changes(trigger=trigger)


async def get_health_status(db: AsyncSession) -> CrawlerHealthStatus:
    """Get overall crawler health status."""
    # Query last run, count active/total pages, determine health
    pass


async def list_snapshots(
    db: AsyncSession,
    page_name: str | None = None,
    changes_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[NtaSnapshotDetail]:
    """List snapshots with optional filters."""
    pass


async def get_snapshot_detail(
    db: AsyncSession, snapshot_id: int
) -> NtaSnapshotDetail:
    """Get full snapshot detail including markdown content."""
    pass


async def get_snapshot_markdown(
    db: AsyncSession, snapshot_id: int
) -> str:
    """Get just the fit_markdown for a snapshot (for copy/paste)."""
    pass


async def upsert_target_page(
    db: AsyncSession, config: NtaTargetPageConfig
) -> NtaTargetPage:
    """Add or update a target NTA page."""
    pass


async def list_target_pages(db: AsyncSession) -> list[NtaTargetPage]:
    """List all target pages."""
    result = await db.execute(
        select(NtaTargetPage).order_by(NtaTargetPage.name)
    )
    return list(result.scalars().all())


async def list_crawler_runs(
    db: AsyncSession, limit: int = 20
) -> list[CrawlerRunSummary]:
    """List recent crawler runs."""
    pass
```

### Task 6B.7: API Routes

**File:** `backend/src/api/nta_routes.py`

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.nta_service import (
    get_health_status,
    get_snapshot_detail,
    get_snapshot_markdown,
    list_crawler_runs,
    list_snapshots,
    list_target_pages,
    trigger_crawl,
    upsert_target_page,
)
from src.domain.schemas import (
    CrawlerHealthStatus,
    CrawlerRunSummary,
    NtaPageChange,
    NtaSnapshotDetail,
    NtaTargetPageConfig,
)
from src.infrastructure.database import get_db

router = APIRouter(prefix="/admin/nta", tags=["Admin - NTA Crawler"])


@router.post(
    "/check-now",
    response_model=list[NtaPageChange],
    summary="Trigger a manual crawler run",
)
async def check_now(db: AsyncSession = Depends(get_db)):
    return await trigger_crawl(db, trigger="MANUAL")


@router.get(
    "/health",
    response_model=CrawlerHealthStatus,
    summary="Get crawler health status",
)
async def get_health(db: AsyncSession = Depends(get_db)):
    return await get_health_status(db)


@router.get(
    "/snapshots",
    response_model=list[NtaSnapshotDetail],
    summary="List snapshots with optional filters",
)
async def get_snapshots(
    page_name: str | None = Query(None, description="Filter by page name"),
    changes_only: bool = Query(False, description="Show only changed snapshots"),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await list_snapshots(db, page_name, changes_only, limit, offset)


@router.get(
    "/snapshots/{snapshot_id}",
    response_model=NtaSnapshotDetail,
    summary="Get full snapshot detail including markdown",
)
async def get_snapshot(snapshot_id: int, db: AsyncSession = Depends(get_db)):
    return await get_snapshot_detail(db, snapshot_id)


@router.get(
    "/snapshots/{snapshot_id}/markdown",
    summary="Get just the fit_markdown for copy/paste to other LLMs",
)
async def get_markdown(snapshot_id: int, db: AsyncSession = Depends(get_db)):
    markdown = await get_snapshot_markdown(db, snapshot_id)
    return {"fit_markdown": markdown}


@router.get(
    "/targets",
    summary="List all monitored NTA target pages",
)
async def get_targets(db: AsyncSession = Depends(get_db)):
    return await list_target_pages(db)


@router.put(
    "/targets",
    summary="Add or update a target NTA page",
)
async def put_target(
    config: NtaTargetPageConfig, db: AsyncSession = Depends(get_db)
):
    return await upsert_target_page(db, config)


@router.get(
    "/runs",
    response_model=list[CrawlerRunSummary],
    summary="List crawler run history",
)
async def get_runs(db: AsyncSession = Depends(get_db)):
    return await list_crawler_runs(db)
```

**Update `backend/src/main.py`:**

```python
from src.api.nta_routes import router as nta_router

# Inside create_app():
application.include_router(nta_router)
```

### Task 6B.8: Streamlit Admin Page — Crawler Monitor

**File:** `admin/app.py` (new page or section)

The "Crawler Monitor" page has five sections:

**1. Health Overview (top of page):**
- Status indicator: green/yellow/red based on last crawl result
- Last crawl timestamp and result (e.g., "2 pages checked, 0 changed, 0 failed")
- Next scheduled crawl time
- "Run Now" button to trigger manual crawl

**2. Target Pages Management:**
- Table of all monitored NTA pages (name, URL, status: active/disabled, last checked, last changed)
- Add new target page form (name, URL, description, check interval)
- Enable/disable toggle per page
- Quick link to view the actual NTA page in browser

**3. Snapshot History:**
- Filterable timeline of all snapshots (by page, date range, change-only filter)
- Each entry shows: page name, timestamp, hash, status (success/failed/timeout), response time
- Highlight rows where content changed (different hash from previous)
- Click to expand and view:
  - **Rendered markdown** (fit_markdown, nicely formatted)
  - **Raw markdown** (raw_markdown, copyable for pasting into external LLMs)
  - **Copy to clipboard** button for the markdown
  - **Markdown diff** with previous snapshot (green/red highlighting)

**4. Crawl Run Log:**
- Table of all crawler runs (manual and scheduled)
- Each run shows: trigger type, start/end time, duration, pages checked, pages changed, pages failed
- Click to see per-page results for that run

**5. Error Log:**
- Filtered view of failed/timed-out snapshots
- Shows error message, page URL, timestamp
- Helps admin debug connectivity or NTA site issues

### Task 6B.9: Crawler Scheduling

**File:** `backend/src/infrastructure/scheduler.py`

Use APScheduler to run the crawler periodically:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()


async def scheduled_crawl():
    """Periodic crawler job triggered by APScheduler."""
    async with get_async_session() as db:
        monitor = NtaMonitor(db)
        changes = await monitor.check_for_changes(trigger="SCHEDULED")
        if changes:
            logger.info(f"Scheduled crawl detected {len(changes)} changes")
        await db.commit()


def start_scheduler(interval_hours: int = 24):
    """Start the periodic crawler scheduler."""
    scheduler.add_job(
        scheduled_crawl,
        "interval",
        hours=interval_hours,
        id="nta_crawler",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"NTA crawler scheduler started: every {interval_hours} hours")
```

### Task 6B.10: Alembic Migration

```bash
alembic revision --autogenerate -m "add nta_target_pages, nta_page_snapshots, nta_crawler_runs tables"
```

### Task 6B.11: Environment Variables

**File:** `.env.example`

Add:

```bash
# NTA Crawler (Phase 6B)
NTA_CRAWL_INTERVAL_HOURS=24
NTA_CRAWL_RATE_LIMIT_SECONDS=2
```

---

## Security

- Respect NTA `robots.txt` and rate limits (configurable delay between requests)
- Admin-only endpoints for all `/admin/nta/` routes
- No user data involved (public NTA pages only)
- Target page management logged to audit trail
- Stored markdown is public NTA content only — no PII concerns

---

## Test Specification

Per `testing-policy.md`, every task must ship with tests.

### Unit Tests (`tests/infrastructure/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_nta_monitor.py` | `NtaMonitor` | check_page() stores baseline snapshot on first crawl, detects no change when hash matches, detects change when hash differs, handles Crawl4AI failure gracefully, content_hash is SHA-256 of fit_markdown |

### Unit Tests (`tests/application/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_nta_service.py` | `NtaService` | add_target_page CRUD, check_all dispatches to NtaMonitor, get_snapshots pagination, get_health_status green/yellow/red thresholds |

### Integration Tests (`tests/api/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_nta_routes.py` | API endpoints | `POST /admin/nta/check` triggers crawl, `GET /admin/nta/snapshots/{id}` returns markdown, `GET /admin/nta/health` returns status, `POST /admin/nta/pages` creates target page |

### Test Conventions
- Mock `Crawl4AI AsyncWebCrawler` — never make real HTTP calls in tests.
- Use factory fixtures for `NtaTargetPage` and `NtaPageSnapshot` records.
- Test hash computation with known markdown inputs for determinism.

---

## Acceptance Criteria

1. `NtaMonitor.check_for_changes()` fetches pages via Crawl4AI and persists markdown + hash to `NtaPageSnapshot`.
2. Both `raw_markdown` and `fit_markdown` are stored per snapshot.
3. Change detection uses `fit_markdown` hash (more stable than HTML hash).
4. When content changes, both old and new snapshots are stored with full markdown.
5. Admin can trigger a check via Streamlit "Run Now" button or API.
6. Extracted tables (tax rate brackets) are preserved in markdown format and also in `extracted_tables` JSONB.
7. Admin can view rendered markdown, copy raw markdown to clipboard for use with external LLMs.
8. Snapshot markdown diff view shows what changed between two versions (human-readable).
9. Crawler health status shows green/yellow/red based on last run.
10. Admin can add, edit, and disable target pages via Streamlit UI.
11. Failed crawls are logged with error details and visible in the error log.
12. Crawl run history is persisted and viewable with per-page breakdown.
