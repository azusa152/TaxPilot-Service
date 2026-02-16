"""Admin API routes for NTA crawler management."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.nta_service import (
    get_health_status,
    get_snapshot_detail,
    get_snapshot_markdown,
    list_crawler_runs,
    list_snapshots,
    list_target_pages,
    trigger_all_crawls,
    trigger_crawl,
    trigger_egov_crawl,
    trigger_mof_crawl,
    upsert_target_page,
)
from src.domain.enums import CrawlerRunTrigger
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
    summary="Trigger a manual NTA crawler run",
)
async def check_now(db: AsyncSession = Depends(get_db)):
    """Trigger NTA Tax Answer crawler (Layer 1)."""
    return await trigger_crawl(db, trigger=CrawlerRunTrigger.MANUAL)


@router.post(
    "/check-mof",
    response_model=list[NtaPageChange],
    summary="Trigger a manual MOF Tax Reform crawler run",
)
async def check_mof(db: AsyncSession = Depends(get_db)):
    """Trigger MOF Tax Reform monitor (Layer 2)."""
    return await trigger_mof_crawl(db, trigger=CrawlerRunTrigger.MANUAL)


@router.post(
    "/check-egov",
    response_model=list[NtaPageChange],
    summary="Trigger a manual e-Gov Law API crawler run",
)
async def check_egov(db: AsyncSession = Depends(get_db)):
    """Trigger e-Gov Law API client (Layer 3)."""
    return await trigger_egov_crawl(db, trigger=CrawlerRunTrigger.MANUAL)


@router.post(
    "/check-all",
    summary="Trigger all three crawler types (NTA, MOF, e-Gov)",
)
async def check_all(db: AsyncSession = Depends(get_db)):
    """Trigger all three crawler layers sequentially."""
    results = await trigger_all_crawls(db, trigger=CrawlerRunTrigger.MANUAL)
    return {
        "nta_changes": results["nta"],
        "mof_changes": results["mof"],
        "egov_changes": results["egov"],
        "total_changes": len(results["nta"]) + len(results["mof"]) + len(results["egov"]),
    }


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
async def put_target(config: NtaTargetPageConfig, db: AsyncSession = Depends(get_db)):
    return await upsert_target_page(db, config)


@router.get(
    "/runs",
    response_model=list[CrawlerRunSummary],
    summary="List crawler run history",
)
async def get_runs(db: AsyncSession = Depends(get_db)):
    return await list_crawler_runs(db)
