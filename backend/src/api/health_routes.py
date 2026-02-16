from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database import get_db
from src.logging_config import get_logger

router = APIRouter(tags=["Health"])
logger = get_logger(__name__)


class HealthResponse(BaseModel):
    status: str = Field(description="Service health status")
    database: str = Field(description="Database connectivity status")


@router.get("/health", response_model=HealthResponse, summary="Check service health")
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "disconnected"

    status = "healthy" if db_status == "connected" else "degraded"
    return HealthResponse(status=status, database=db_status)
