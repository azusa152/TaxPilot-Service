"""LLM provider configuration and usage tracking service.

Handles CRUD for LLM provider configs and usage summary queries.
Encryption/decryption is delegated to infrastructure/encryption.py.
"""

from datetime import datetime, timezone

from sqlalchemy import func as sqla_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.schemas import LlmConfigCreate, LlmConfigResponse, LlmUsageSummary
from src.infrastructure.encryption import decrypt_token, encrypt_token, mask_token
from src.infrastructure.models import LlmProviderConfig, LlmUsageLog
from src.logging_config import get_logger

logger = get_logger(__name__)


async def upsert_llm_config(db: AsyncSession, data: LlmConfigCreate) -> LlmConfigResponse:
    """Create or update the LLM provider configuration.

    Deactivates all existing configs and creates a new active one.

    Args:
        db: Async database session.
        data: LLM config creation data with provider, model, token, and budget.

    Returns:
        LlmConfigResponse with masked token.
    """
    # Deactivate all existing configs
    existing = await db.execute(select(LlmProviderConfig))
    for config in existing.scalars().all():
        config.is_active = False

    # Create new active config
    config = LlmProviderConfig(
        provider=data.provider,
        model_name=data.model_name,
        encrypted_api_token=encrypt_token(data.api_token),
        is_active=True,
        monthly_budget_usd=data.monthly_budget_usd,
    )
    db.add(config)
    await db.flush()
    await db.refresh(config)

    logger.info(f"LLM config updated: provider={data.provider}, model={data.model_name}")

    return LlmConfigResponse(
        id=config.id,
        provider=config.provider,
        model_name=config.model_name,
        masked_token=mask_token(data.api_token),
        is_active=config.is_active,
        monthly_budget_usd=float(config.monthly_budget_usd),
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


async def get_active_config(db: AsyncSession) -> LlmProviderConfig | None:
    """Get the active LLM provider config (with encrypted token).

    Args:
        db: Async database session.

    Returns:
        Active LlmProviderConfig or None if no config exists.
    """
    result = await db.execute(select(LlmProviderConfig).where(LlmProviderConfig.is_active == True))  # noqa: E712
    return result.scalar_one_or_none()


async def get_decrypted_token(db: AsyncSession) -> tuple[str, str] | None:
    """Get the active model string and decrypted API token.

    Args:
        db: Async database session.

    Returns:
        Tuple of (model_name, api_token) or None if no config exists.
    """
    config = await get_active_config(db)
    if config is None:
        return None
    return config.model_name, decrypt_token(config.encrypted_api_token)


async def get_usage_summary(db: AsyncSession) -> LlmUsageSummary:
    """Get LLM usage summary for the current month.

    Args:
        db: Async database session.

    Returns:
        LlmUsageSummary with totals, daily breakdown, and budget remaining.
    """
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Monthly totals
    totals_result = await db.execute(
        select(
            sqla_func.count(LlmUsageLog.id).label("total_calls"),
            sqla_func.coalesce(sqla_func.sum(LlmUsageLog.prompt_tokens), 0).label("total_prompt_tokens"),
            sqla_func.coalesce(sqla_func.sum(LlmUsageLog.completion_tokens), 0).label("total_completion_tokens"),
            sqla_func.coalesce(sqla_func.sum(LlmUsageLog.cost_usd), 0).label("total_cost_usd"),
        ).where(LlmUsageLog.created_at >= month_start)
    )
    totals = totals_result.one()

    # Daily breakdown
    daily_result = await db.execute(
        select(
            sqla_func.date_trunc("day", LlmUsageLog.created_at).label("day"),
            sqla_func.count(LlmUsageLog.id).label("calls"),
            sqla_func.coalesce(sqla_func.sum(LlmUsageLog.cost_usd), 0).label("cost_usd"),
        )
        .where(LlmUsageLog.created_at >= month_start)
        .group_by(sqla_func.date_trunc("day", LlmUsageLog.created_at))
        .order_by(sqla_func.date_trunc("day", LlmUsageLog.created_at))
    )
    daily_breakdown = [
        {"date": str(row.day.date()), "calls": row.calls, "cost_usd": float(row.cost_usd)} for row in daily_result
    ]

    # Get budget from active config
    config = await get_active_config(db)
    budget = float(config.monthly_budget_usd) if config else 50.00
    monthly_total = float(totals.total_cost_usd)

    return LlmUsageSummary(
        total_calls=totals.total_calls,
        total_prompt_tokens=totals.total_prompt_tokens,
        total_completion_tokens=totals.total_completion_tokens,
        total_cost_usd=monthly_total,
        daily_breakdown=daily_breakdown,
        monthly_total_usd=monthly_total,
        budget_remaining_usd=max(0.0, budget - monthly_total),
    )
