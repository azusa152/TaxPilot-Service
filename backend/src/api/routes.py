"""FastAPI route handlers — thin controllers that delegate to services."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database import get_session

router = APIRouter()


@router.get("/health", tags=["system"])
async def health_check(session: AsyncSession = Depends(get_session)) -> dict:
    """Verify API and database connectivity.

    Executes a simple query against PostgreSQL to confirm the
    database connection is active.

    Returns:
        Dictionary with service status and database connectivity result.
    """
    await session.execute(text("SELECT 1"))
    return {"status": "healthy", "database": "connected"}
