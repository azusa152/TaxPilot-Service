"""Tests for application/llm_config_service.py — LLM configuration CRUD and usage summary."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from src.application.llm_config_service import (
    get_active_config,
    get_decrypted_token,
    get_usage_summary,
    upsert_llm_config,
)
from src.domain.enums import LlmProvider
from src.domain.schemas import LlmConfigCreate
from src.infrastructure.models import LlmProviderConfig, LlmUsageLog


@pytest.fixture()
def fernet_key():
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


class TestUpsertLlmConfig:
    """Tests for upsert_llm_config()."""

    @patch("src.application.llm_config_service.encrypt_token", return_value="encrypted_value")
    @patch("src.application.llm_config_service.mask_token", return_value="sk-...6789")
    async def test_creates_new_config(self, mock_mask, mock_encrypt, db_session):
        data = LlmConfigCreate(
            provider=LlmProvider.OPENAI,
            model_name="openai/gpt-4o",
            api_token="sk-test123456789",
            monthly_budget_usd=75.00,
        )

        result = await upsert_llm_config(db_session, data)

        assert result.provider == "openai"
        assert result.model_name == "openai/gpt-4o"
        assert result.masked_token == "sk-...6789"
        assert result.is_active is True
        assert result.monthly_budget_usd == 75.00

    @patch("src.application.llm_config_service.encrypt_token", return_value="encrypted_new")
    @patch("src.application.llm_config_service.mask_token", return_value="ge-...wxyz")
    async def test_deactivates_previous_config(self, mock_mask, mock_encrypt, db_session):
        # Create initial config
        old_config = LlmProviderConfig(
            provider="openai",
            model_name="openai/gpt-4o",
            encrypted_api_token="encrypted_old",
            is_active=True,
            monthly_budget_usd=50.00,
        )
        db_session.add(old_config)
        await db_session.flush()

        # Upsert new config
        data = LlmConfigCreate(
            provider=LlmProvider.GEMINI,
            model_name="gemini/gemini-2.0-flash",
            api_token="gemini-token-abcwxyz",
            monthly_budget_usd=100.00,
        )
        result = await upsert_llm_config(db_session, data)

        assert result.provider == "gemini"
        assert result.is_active is True

        # Verify old config is deactivated
        all_configs = await db_session.execute(select(LlmProviderConfig))
        configs = all_configs.scalars().all()
        active = [c for c in configs if c.is_active]
        assert len(active) == 1
        assert active[0].provider == "gemini"


class TestGetActiveConfig:
    """Tests for get_active_config()."""

    async def test_returns_none_when_empty(self, db_session):
        result = await get_active_config(db_session)
        assert result is None

    async def test_returns_active_config(self, db_session):
        config = LlmProviderConfig(
            provider="anthropic",
            model_name="anthropic/claude-sonnet-4-20250514",
            encrypted_api_token="encrypted_token",
            is_active=True,
            monthly_budget_usd=30.00,
        )
        db_session.add(config)
        await db_session.flush()

        result = await get_active_config(db_session)
        assert result is not None
        assert result.provider == "anthropic"
        assert result.is_active is True


class TestGetDecryptedToken:
    """Tests for get_decrypted_token()."""

    async def test_returns_none_when_no_config(self, db_session):
        result = await get_decrypted_token(db_session)
        assert result is None

    @patch("src.application.llm_config_service.decrypt_token", return_value="decrypted-token")
    async def test_returns_model_and_token(self, mock_decrypt, db_session):
        config = LlmProviderConfig(
            provider="openai",
            model_name="openai/gpt-4o",
            encrypted_api_token="encrypted_data",
            is_active=True,
            monthly_budget_usd=50.00,
        )
        db_session.add(config)
        await db_session.flush()

        result = await get_decrypted_token(db_session)
        assert result == ("openai/gpt-4o", "decrypted-token")


class TestGetUsageSummary:
    """Tests for get_usage_summary()."""

    async def test_empty_usage_returns_zeros(self, db_session):
        # Add config for budget
        config = LlmProviderConfig(
            provider="openai",
            model_name="openai/gpt-4o",
            encrypted_api_token="enc",
            is_active=True,
            monthly_budget_usd=50.00,
        )
        db_session.add(config)
        await db_session.flush()

        result = await get_usage_summary(db_session)
        assert result.total_calls == 0
        assert result.total_prompt_tokens == 0
        assert result.total_completion_tokens == 0
        assert result.total_cost_usd == 0.0
        assert result.monthly_total_usd == 0.0
        assert result.budget_remaining_usd == 50.0
        assert result.daily_breakdown == []

    async def test_aggregates_usage_correctly(self, db_session):
        config = LlmProviderConfig(
            provider="openai",
            model_name="openai/gpt-4o",
            encrypted_api_token="enc",
            is_active=True,
            monthly_budget_usd=100.00,
        )
        db_session.add(config)

        # Add some usage logs
        for i in range(3):
            log = LlmUsageLog(
                provider="openai",
                model="openai/gpt-4o",
                prompt_tokens=100,
                completion_tokens=50,
                cost_usd=0.01,
            )
            db_session.add(log)
        await db_session.flush()

        result = await get_usage_summary(db_session)
        assert result.total_calls == 3
        assert result.total_prompt_tokens == 300
        assert result.total_completion_tokens == 150
        assert float(result.total_cost_usd) == pytest.approx(0.03, abs=1e-6)
        assert result.budget_remaining_usd == pytest.approx(99.97, abs=1e-2)
