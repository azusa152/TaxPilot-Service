"""Tests for infrastructure/llm_service.py — LlmService wrapper around LiteLLM."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from src.domain.exceptions import LlmCallError
from src.infrastructure.llm_service import LlmService
from src.infrastructure.models import LlmProviderConfig, LlmUsageLog


class SampleResponse(BaseModel):
    """Sample Pydantic model for structured output tests."""

    answer: str
    confidence: float


def _make_mock_response(content: str, prompt_tokens: int = 10, completion_tokens: int = 20):
    """Create a mock LiteLLM response object."""
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    response = MagicMock()
    response.usage = usage
    response.choices = [choice]
    return response


@pytest.fixture()
async def db_with_config(db_session):
    """DB session with an active LLM provider config."""
    config = LlmProviderConfig(
        provider="openai",
        model_name="openai/gpt-4o",
        # Encrypted token placeholder — we mock decrypt_token in tests
        encrypted_api_token="encrypted_placeholder",
        is_active=True,
        monthly_budget_usd=50.00,
    )
    db_session.add(config)
    await db_session.flush()
    return db_session


class TestGenerate:
    """Tests for LlmService.generate()."""

    @patch("src.infrastructure.llm_service.decrypt_token", return_value="sk-test-token")
    @patch("src.infrastructure.llm_service.litellm")
    async def test_generate_returns_text(self, mock_litellm, mock_decrypt, db_with_config):
        mock_litellm.acompletion = AsyncMock(return_value=_make_mock_response("Hello TaxPilot!"))
        mock_litellm.completion_cost = MagicMock(return_value=0.001)
        mock_litellm.enable_json_schema_validation = True

        service = LlmService(db_with_config)
        result = await service.generate(
            messages=[{"role": "user", "content": "Say hello"}],
            caller="test",
        )

        assert result == "Hello TaxPilot!"
        mock_litellm.acompletion.assert_awaited_once()
        # Verify api_key passed as parameter (not set on global)
        call_kwargs = mock_litellm.acompletion.call_args.kwargs
        assert call_kwargs["api_key"] == "sk-test-token"

    @patch("src.infrastructure.llm_service.decrypt_token", return_value="sk-test-token")
    @patch("src.infrastructure.llm_service.litellm")
    async def test_generate_logs_usage(self, mock_litellm, mock_decrypt, db_with_config):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_mock_response("response", prompt_tokens=15, completion_tokens=25)
        )
        mock_litellm.completion_cost = MagicMock(return_value=0.002)
        mock_litellm.enable_json_schema_validation = True

        service = LlmService(db_with_config)
        await service.generate(
            messages=[{"role": "user", "content": "test"}],
            caller="regulation_parser",
        )

        result = await db_with_config.execute(select(LlmUsageLog))
        log = result.scalar_one()
        assert log.provider == "openai"
        assert log.model == "openai/gpt-4o"
        assert log.prompt_tokens == 15
        assert log.completion_tokens == 25
        assert float(log.cost_usd) == 0.002
        assert log.caller == "regulation_parser"

    @patch("src.infrastructure.llm_service.decrypt_token", return_value="sk-test-token")
    @patch("src.infrastructure.llm_service.litellm")
    async def test_generate_budget_exceeded_raises(self, mock_litellm, mock_decrypt, db_with_config):
        mock_litellm.enable_json_schema_validation = True

        # Add usage that exceeds budget
        log = LlmUsageLog(
            provider="openai",
            model="openai/gpt-4o",
            prompt_tokens=100000,
            completion_tokens=50000,
            cost_usd=55.00,  # Exceeds the 50.00 budget
        )
        db_with_config.add(log)
        await db_with_config.flush()

        service = LlmService(db_with_config)
        with pytest.raises(ValueError, match="Monthly LLM budget exceeded"):
            await service.generate(
                messages=[{"role": "user", "content": "test"}],
            )

    @patch("src.infrastructure.llm_service.decrypt_token", return_value="sk-test-token")
    @patch("src.infrastructure.llm_service.litellm")
    async def test_generate_api_error_raises_llm_call_error(self, mock_litellm, mock_decrypt, db_with_config):
        mock_litellm.enable_json_schema_validation = True
        mock_litellm.exceptions.APIError = type("APIError", (Exception,), {})
        mock_litellm.acompletion = AsyncMock(side_effect=mock_litellm.exceptions.APIError("auth failed"))

        service = LlmService(db_with_config)
        with pytest.raises(LlmCallError, match="LLM API error"):
            await service.generate(
                messages=[{"role": "user", "content": "test"}],
            )

    @patch("src.infrastructure.llm_service.decrypt_token", return_value="sk-test-token")
    @patch("src.infrastructure.llm_service.litellm")
    async def test_generate_unexpected_error_raises_llm_call_error(self, mock_litellm, mock_decrypt, db_with_config):
        mock_litellm.enable_json_schema_validation = True
        mock_litellm.exceptions.APIError = type("APIError", (Exception,), {})
        mock_litellm.acompletion = AsyncMock(side_effect=ConnectionError("network down"))

        service = LlmService(db_with_config)
        with pytest.raises(LlmCallError, match="LLM call failed unexpectedly"):
            await service.generate(
                messages=[{"role": "user", "content": "test"}],
            )


class TestGenerateStructured:
    """Tests for LlmService.generate_structured()."""

    @patch("src.infrastructure.llm_service.decrypt_token", return_value="sk-test-token")
    @patch("src.infrastructure.llm_service.litellm")
    async def test_generate_structured_returns_model(self, mock_litellm, mock_decrypt, db_with_config):
        response_json = '{"answer": "42", "confidence": 0.95}'
        mock_litellm.acompletion = AsyncMock(return_value=_make_mock_response(response_json))
        mock_litellm.completion_cost = MagicMock(return_value=0.001)
        mock_litellm.enable_json_schema_validation = True

        service = LlmService(db_with_config)
        result = await service.generate_structured(
            messages=[{"role": "user", "content": "What is the answer?"}],
            response_format=SampleResponse,
            caller="test",
        )

        assert isinstance(result, SampleResponse)
        assert result.answer == "42"
        assert result.confidence == 0.95
        # Verify api_key passed as parameter
        call_kwargs = mock_litellm.acompletion.call_args.kwargs
        assert call_kwargs["api_key"] == "sk-test-token"

    @patch("src.infrastructure.llm_service.decrypt_token", return_value="sk-test-token")
    @patch("src.infrastructure.llm_service.litellm")
    async def test_generate_structured_api_error_raises(self, mock_litellm, mock_decrypt, db_with_config):
        mock_litellm.enable_json_schema_validation = True
        mock_litellm.exceptions.APIError = type("APIError", (Exception,), {})
        mock_litellm.acompletion = AsyncMock(side_effect=mock_litellm.exceptions.APIError("rate limited"))

        service = LlmService(db_with_config)
        with pytest.raises(LlmCallError, match="LLM API error"):
            await service.generate_structured(
                messages=[{"role": "user", "content": "test"}],
                response_format=SampleResponse,
            )


class TestGenerateFallbackToEnv:
    """Tests that LlmService falls back to env vars when no DB config exists."""

    @patch("src.infrastructure.llm_service.settings")
    @patch("src.infrastructure.llm_service.litellm")
    async def test_falls_back_to_env(self, mock_litellm, mock_settings, db_session):
        mock_settings.llm_model = "gemini/gemini-2.0-flash"
        mock_settings.llm_api_token = "env-token"
        mock_settings.llm_monthly_budget_usd = 100.0

        mock_litellm.acompletion = AsyncMock(return_value=_make_mock_response("Hello from Gemini"))
        mock_litellm.completion_cost = MagicMock(return_value=0.0005)
        mock_litellm.enable_json_schema_validation = True

        service = LlmService(db_session)
        result = await service.generate(
            messages=[{"role": "user", "content": "test"}],
        )

        assert result == "Hello from Gemini"
        # Verify the API key was passed as parameter
        call_kwargs = mock_litellm.acompletion.call_args.kwargs
        assert call_kwargs["api_key"] == "env-token"


class TestTestConnection:
    """Tests for LlmService.test_connection()."""

    @patch("src.infrastructure.llm_service.decrypt_token", return_value="sk-test-token")
    @patch("src.infrastructure.llm_service.litellm")
    async def test_connection_returns_status(self, mock_litellm, mock_decrypt, db_with_config):
        mock_litellm.acompletion = AsyncMock(return_value=_make_mock_response("Hello TaxPilot!"))
        mock_litellm.completion_cost = MagicMock(return_value=0.001)
        mock_litellm.enable_json_schema_validation = True

        service = LlmService(db_with_config)
        result = await service.test_connection()

        assert result["status"] == "ok"
        assert result["model"] == "openai/gpt-4o"
        assert result["response"] == "Hello TaxPilot!"
        assert "latency_seconds" in result
