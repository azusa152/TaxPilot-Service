from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str = Field(description="Service health status")
    database: str = Field(description="Database connectivity status")


@router.get("/health", response_model=HealthResponse, summary="Check service health")
async def health_check() -> HealthResponse:
    # Phase 1: basic health check. Phase 2 will add actual DB connectivity test.
    return HealthResponse(status="healthy", database="not_configured")
