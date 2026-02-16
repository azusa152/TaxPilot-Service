"""LLM service wrapping LiteLLM for multi-provider access.

Reads config from DB (preferred) or falls back to env vars.
Logs usage and cost. Enforces monthly budget cap.
"""

import time
from datetime import datetime, timezone

import litellm
from pydantic import BaseModel
from sqlalchemy import func as sqla_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.llm_config_service import get_active_config
from src.config import settings
from src.domain.exceptions import LlmCallError
from src.infrastructure.encryption import decrypt_token
from src.infrastructure.models import LlmUsageLog
from src.logging_config import get_logger

logger = get_logger(__name__)

# Enable client-side JSON schema validation as fallback
litellm.enable_json_schema_validation = True


class LlmService:
    """Wrapper around LiteLLM for multi-provider LLM access.

    Reads config from DB (preferred) or falls back to env vars.
    Logs usage and cost. Enforces monthly budget cap.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_config(self) -> tuple[str, str, float]:
        """Get model, token, and budget from DB or env vars.

        Returns:
            Tuple of (model_name, api_token, monthly_budget_usd).
        """
        config = await get_active_config(self.db)
        if config:
            token = decrypt_token(config.encrypted_api_token)
            return config.model_name, token, float(config.monthly_budget_usd)
        # Fallback to pydantic-settings
        return settings.llm_model, settings.llm_api_token, settings.llm_monthly_budget_usd

    async def _check_budget(self, budget: float) -> None:
        """Check if monthly budget is exceeded.

        Args:
            budget: Monthly budget cap in USD.

        Raises:
            ValueError: If current month's spend meets or exceeds the budget.
        """
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        result = await self.db.execute(
            select(sqla_func.coalesce(sqla_func.sum(LlmUsageLog.cost_usd), 0)).where(
                LlmUsageLog.created_at >= month_start
            )
        )
        current_spend = float(result.scalar_one())

        if current_spend >= budget:
            raise ValueError(
                f"Monthly LLM budget exceeded: ${current_spend:.2f} spent of ${budget:.2f} budget. "
                "Increase the budget via admin settings or wait until next month."
            )

    async def _log_usage(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float | None,
        caller: str | None = None,
        evolution_run_id: int | None = None,
    ) -> None:
        """Log LLM usage to the database.

        Args:
            provider: LLM provider name.
            model: LiteLLM model string.
            prompt_tokens: Number of prompt tokens used.
            completion_tokens: Number of completion tokens used.
            cost_usd: Cost of the call in USD.
            caller: Identifier for the calling component.
            evolution_run_id: Optional link to an evolution run.
        """
        log = LlmUsageLog(
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            caller=caller,
            evolution_run_id=evolution_run_id,
        )
        self.db.add(log)
        await self.db.flush()

    async def generate(
        self,
        messages: list[dict[str, str]],
        caller: str | None = None,
        evolution_run_id: int | None = None,
    ) -> str:
        """Generate a text response from the LLM.

        Args:
            messages: Chat messages in OpenAI format [{"role": ..., "content": ...}].
            caller: Identifier for the calling component (for usage tracking).
            evolution_run_id: Optional link to an evolution run.

        Returns:
            The LLM's text response.

        Raises:
            ValueError: If monthly budget is exceeded.
            LlmCallError: If the LLM API call fails.
        """
        model, token, budget = await self._get_config()
        await self._check_budget(budget)

        provider = model.split("/")[0] if "/" in model else "openai"

        try:
            response = await litellm.acompletion(model=model, messages=messages, api_key=token)
        except litellm.exceptions.APIError as e:
            logger.error(f"LLM API error: {e}")
            raise LlmCallError(f"LLM API error: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected LLM error: {e}")
            raise LlmCallError(f"LLM call failed unexpectedly: {e}") from e

        usage = response.usage
        cost = litellm.completion_cost(completion_response=response)

        await self._log_usage(
            provider=provider,
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cost_usd=cost,
            caller=caller,
            evolution_run_id=evolution_run_id,
        )

        logger.info(
            f"LLM call: model={model}, tokens={usage.prompt_tokens}+{usage.completion_tokens}, cost=${cost:.4f}"
        )
        return response.choices[0].message.content

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        response_format: type[BaseModel],
        caller: str | None = None,
        evolution_run_id: int | None = None,
    ) -> BaseModel:
        """Generate a structured response validated against a Pydantic model.

        Uses LiteLLM's response_format parameter for provider-native JSON schema
        enforcement, with client-side Pydantic validation as fallback.

        Args:
            messages: Chat messages in OpenAI format.
            response_format: Pydantic model class for response validation.
            caller: Identifier for the calling component.
            evolution_run_id: Optional link to an evolution run.

        Returns:
            Validated Pydantic model instance.

        Raises:
            ValueError: If monthly budget is exceeded.
            LlmCallError: If the LLM API call fails.
        """
        model, token, budget = await self._get_config()
        await self._check_budget(budget)

        provider = model.split("/")[0] if "/" in model else "openai"

        try:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                response_format=response_format,
                api_key=token,
            )
        except litellm.exceptions.APIError as e:
            logger.error(f"LLM structured API error: {e}")
            raise LlmCallError(f"LLM API error: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected LLM structured error: {e}")
            raise LlmCallError(f"LLM call failed unexpectedly: {e}") from e

        usage = response.usage
        cost = litellm.completion_cost(completion_response=response)

        await self._log_usage(
            provider=provider,
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cost_usd=cost,
            caller=caller,
            evolution_run_id=evolution_run_id,
        )

        result = response_format.model_validate_json(response.choices[0].message.content)

        logger.info(
            f"LLM structured call: model={model}, format={response_format.__name__}, "
            f"tokens={usage.prompt_tokens}+{usage.completion_tokens}, cost=${cost:.4f}"
        )
        return result

    async def test_connection(self) -> dict:
        """Test the LLM connection with a simple prompt.

        Returns:
            Dict with model, response text, cost, and latency.
        """
        model, _, _ = await self._get_config()

        start = time.time()
        response_text = await self.generate(
            messages=[{"role": "user", "content": "Say 'Hello TaxPilot' in one sentence."}],
            caller="connection_test",
        )
        elapsed = time.time() - start

        return {
            "model": model,
            "response": response_text,
            "latency_seconds": round(elapsed, 2),
            "status": "ok",
        }
