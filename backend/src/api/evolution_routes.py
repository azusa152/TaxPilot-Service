"""API routes for Evolution Loop — admin pipeline management and review."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.evolution_service import EvolutionPipeline
from src.domain.enums import EvolutionRunStatus
from src.domain.schemas import (
    EvolutionRunDetail,
    EvolutionRunSummary,
    ReviewRequest,
)
from src.infrastructure.database import get_db
from src.infrastructure.models import EvolutionRun, GenerationAttempt, SchemaChangeProposalRecord

router = APIRouter(prefix="/admin/evolution", tags=["Admin - Evolution Loop"])


@router.post(
    "/run",
    summary="Start a new evolution pipeline run",
    description="Triggers the full pipeline: crawl → parse → generate → await review. "
                "Optionally process a specific snapshot instead of crawling.",
)
async def start_evolution_run(
    snapshot_id: int | None = Query(
        None, description="Specific snapshot to process (optional)"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Start a new evolution pipeline run.

    Returns:
        run_id: ID of the created evolution run
        status: Current status (usually PENDING or CRAWLING)
    """
    pipeline = EvolutionPipeline(db)
    run = await pipeline.start_run(trigger="MANUAL", snapshot_id=snapshot_id)
    await db.commit()
    return {"run_id": run.id, "status": run.status}


@router.get(
    "/runs",
    response_model=list[EvolutionRunSummary],
    summary="List all evolution runs with optional status filter",
    description="Returns a list of evolution runs with pagination and optional status filtering.",
)
async def list_runs(
    status: str | None = Query(None, description="Filter by status (e.g., AWAITING_REVIEW, ACCEPTED)"),
    limit: int = Query(20, le=100, description="Maximum number of runs to return"),
    offset: int = Query(0, ge=0, description="Number of runs to skip"),
    db: AsyncSession = Depends(get_db),
):
    """List evolution runs with optional filtering.

    Returns:
        List of EvolutionRunSummary objects with id, trigger, status, timestamps.
    """
    query = select(EvolutionRun).order_by(EvolutionRun.started_at.desc())

    if status:
        query = query.where(EvolutionRun.status == status)

    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    runs = result.scalars().all()

    return [
        EvolutionRunSummary(
            id=run.id,
            trigger=run.trigger,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            review_decision=run.review_decision,
        )
        for run in runs
    ]


@router.get(
    "/runs/{run_id}",
    response_model=EvolutionRunDetail,
    summary="Get detailed view of an evolution run",
    description="Returns full details including parsed changes, generation attempts, and schema proposals.",
)
async def get_run(run_id: int, db: AsyncSession = Depends(get_db)):
    """Get detailed view of an evolution run.

    Returns:
        EvolutionRunDetail with all generation attempts and schema proposal.
    """
    run = await db.get(EvolutionRun, run_id)
    if run is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Evolution run {run_id} not found")

    # Get all generation attempts for this run
    attempts_result = await db.execute(
        select(GenerationAttempt)
        .where(GenerationAttempt.evolution_run_id == run_id)
        .order_by(GenerationAttempt.attempt_number)
    )
    attempts = attempts_result.scalars().all()

    generation_attempts = [
        {
            "attempt_number": att.attempt_number,
            "generated_code": att.generated_code,
            "validation_passed": att.validation_passed,
            "validation_errors": att.validation_errors,
            "admin_hints": att.admin_hints,
            "created_at": att.created_at.isoformat(),
        }
        for att in attempts
    ]

    # Get schema proposal if exists
    schema_proposal = None
    if run.schema_proposal_id:
        proposal = await db.get(SchemaChangeProposalRecord, run.schema_proposal_id)
        if proposal:
            schema_proposal = {
                "id": proposal.id,
                "new_fields": proposal.new_fields,
                "modified_fields": proposal.modified_fields,
                "status": proposal.status,
                "created_at": proposal.created_at.isoformat(),
            }

    return EvolutionRunDetail(
        id=run.id,
        trigger=run.trigger,
        status=run.status,
        nta_snapshot_id=run.nta_snapshot_id,
        parsed_changes=run.parsed_changes,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
        review_decision=run.review_decision,
        rationale=run.rationale,
        regeneration_count=run.regeneration_count,
        max_regenerations=run.max_regenerations,
        generation_attempts=generation_attempts,
        schema_proposal=schema_proposal,
    )


@router.post(
    "/runs/{run_id}/review",
    summary="Submit admin review decision",
    description="Process admin decision: ACCEPT, MODIFY, REGENERATE, SKIP_PERMANENT, or SKIP_MANUAL.",
)
async def submit_review(
    run_id: int,
    review: ReviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """Submit admin review decision for an evolution run.

    Args:
        run_id: ID of the evolution run to review
        review: Review decision with rationale and optional code/hints

    Returns:
        run_id: ID of the run
        status: Updated status after review
    """
    pipeline = EvolutionPipeline(db)
    run = await pipeline.submit_review(run_id, review, actor="admin")
    await db.commit()
    return {"run_id": run.id, "status": run.status}


@router.post(
    "/runs/{run_id}/rollback",
    summary="Rollback to previous algorithm version",
    description="Re-activates the previous ARCHIVED algorithm and archives the current ACTIVE one.",
)
async def rollback_run(
    run_id: int, db: AsyncSession = Depends(get_db)
):
    """Rollback an evolution run to the previous algorithm version.

    Args:
        run_id: ID of the evolution run to rollback

    Returns:
        message: Confirmation message
    """
    pipeline = EvolutionPipeline(db)
    await pipeline.rollback(run_id, actor="admin")
    await db.commit()
    return {"message": f"Rollback completed for run {run_id}"}


@router.get(
    "/deferred",
    response_model=list[EvolutionRunSummary],
    summary="List all deferred runs awaiting manual handling",
    description="Returns runs with status=DEFERRED that were marked for manual handling later.",
)
async def list_deferred(
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """List all deferred evolution runs.

    Returns:
        List of EvolutionRunSummary objects with status=DEFERRED.
    """
    result = await db.execute(
        select(EvolutionRun)
        .where(EvolutionRun.status == EvolutionRunStatus.DEFERRED)
        .order_by(EvolutionRun.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    runs = result.scalars().all()

    return [
        EvolutionRunSummary(
            id=run.id,
            trigger=run.trigger,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            review_decision=run.review_decision,
        )
        for run in runs
    ]
