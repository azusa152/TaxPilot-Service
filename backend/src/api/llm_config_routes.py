"""API routes for LLM provider configuration and usage tracking."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.llm_config_service import get_active_config, get_usage_summary, upsert_llm_config
from src.domain.schemas import LlmConfigCreate, LlmConfigResponse, LlmUsageSummary
from src.infrastructure.database import get_db
from src.infrastructure.encryption import decrypt_token, mask_token
from src.infrastructure.llm_service import LlmService

router = APIRouter(prefix="/admin/llm", tags=["Admin - LLM Configuration"])


@router.put(
    "/config",
    response_model=LlmConfigResponse,
    summary="Create or update LLM provider configuration",
)
async def put_llm_config(data: LlmConfigCreate, db: AsyncSession = Depends(get_db)):
    """Store LLM provider configuration with encrypted API token."""
    return await upsert_llm_config(db, data)


@router.get(
    "/config",
    response_model=LlmConfigResponse | None,
    summary="Get current LLM provider configuration (token masked)",
)
async def get_llm_config(db: AsyncSession = Depends(get_db)):
    """Retrieve the active LLM provider configuration with masked token."""
    config = await get_active_config(db)
    if config is None:
        return None
    return LlmConfigResponse(
        id=config.id,
        provider=config.provider,
        model_name=config.model_name,
        masked_token=mask_token(decrypt_token(config.encrypted_api_token)),
        is_active=config.is_active,
        monthly_budget_usd=float(config.monthly_budget_usd),
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.post(
    "/test",
    summary="Test LLM connection with a simple prompt",
)
async def test_llm_connection(db: AsyncSession = Depends(get_db)):
    """Test the LLM connection by sending a simple prompt and measuring latency."""
    service = LlmService(db)
    return await service.test_connection()


@router.get(
    "/usage",
    response_model=LlmUsageSummary,
    summary="Get LLM usage and cost summary for the current month",
)
async def get_llm_usage(db: AsyncSession = Depends(get_db)):
    """Retrieve LLM usage statistics and cost breakdown for the current month."""
    return await get_usage_summary(db)
