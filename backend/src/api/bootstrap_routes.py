"""Admin API routes for bootstrap and verification."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import AlgorithmStatus
from src.infrastructure.bootstrap import BootstrapRunner
from src.infrastructure.database import get_db
from src.infrastructure.llm_service import LlmService
from src.infrastructure.models import AlgorithmRegistry, BootstrapVerificationReport

router = APIRouter(prefix="/admin/bootstrap", tags=["Admin - Bootstrap"])


@router.post(
    "/run",
    summary="Run the bootstrap process (seed registry + optional verification)",
)
async def run_bootstrap(
    skip_crawl: bool = Query(
        False, description="Skip the NTA crawl step (useful for environments without internet)"
    ),
    skip_verification: bool = Query(
        False, description="Skip the LLM verification step"
    ),
    db: AsyncSession = Depends(get_db),
):
    llm = LlmService(db) if not skip_verification else None
    runner = BootstrapRunner(db=db, llm_service=llm)
    return await runner.run(skip_crawl=skip_crawl, skip_verification=skip_verification)


@router.post(
    "/verify",
    summary="Re-run LLM verification only (useful after prompt improvements)",
)
async def run_verification(db: AsyncSession = Depends(get_db)):
    llm = LlmService(db)
    runner = BootstrapRunner(db=db, llm_service=llm)
    return await runner.run_verification_only()


@router.get(
    "/report",
    summary="Get the latest verification report",
)
async def get_report(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BootstrapVerificationReport).order_by(
            BootstrapVerificationReport.created_at.desc()
        )
    )
    reports = result.scalars().all()

    return {
        "total": len(reports),
        "reports": [
            {
                "function_name": r.function_name,
                "nta_page_name": r.nta_page_name,
                "verification_status": r.verification_status,
                "confidence_score": float(r.confidence_score),
                "llm_extracted_rules": r.llm_extracted_rules,
                "details": r.details,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ],
    }


@router.get(
    "/status",
    summary="Get bootstrap status (registry and verification state)",
)
async def get_status(db: AsyncSession = Depends(get_db)):
    # Check AlgorithmRegistry for ACTIVE entries
    algo_result = await db.execute(
        select(AlgorithmRegistry).where(
            AlgorithmRegistry.status == AlgorithmStatus.ACTIVE
        )
    )
    algorithms = algo_result.scalars().all()

    # Check for verification reports
    report_result = await db.execute(
        select(BootstrapVerificationReport).order_by(
            BootstrapVerificationReport.created_at.desc()
        ).limit(1)
    )
    latest_report = report_result.scalar_one_or_none()

    return {
        "bootstrap_completed": len(algorithms) > 0,
        "registered_algorithms": [
            {
                "function_name": a.function_name,
                "version": a.version,
                "status": a.status,
                "source_law_hash": a.source_law_hash,
            }
            for a in algorithms
        ],
        "verification_available": latest_report is not None,
        "last_verification_at": (
            latest_report.created_at.isoformat()
            if latest_report and latest_report.created_at
            else None
        ),
    }
