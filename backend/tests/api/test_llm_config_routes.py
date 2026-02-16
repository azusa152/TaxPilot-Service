"""Integration tests for api/llm_config_routes.py — LLM configuration endpoints."""

from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.models import LlmProviderConfig


class TestPutLlmConfig:
    """Tests for PUT /admin/llm/config."""

    @patch("src.infrastructure.encryption.settings")
    async def test_creates_config_and_returns_masked(self, mock_settings, client, db_session):
        from cryptography.fernet import Fernet

        mock_settings.llm_encryption_key = Fernet.generate_key().decode()

        response = await client.put(
            "/admin/llm/config",
            json={
                "provider": "openai",
                "model_name": "openai/gpt-4o",
                "api_token": "sk-test123456789abc",
                "monthly_budget_usd": 75.0,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "openai"
        assert data["model_name"] == "openai/gpt-4o"
        assert data["is_active"] is True
        assert data["monthly_budget_usd"] == 75.0
        # Token should be masked
        assert "sk-test123456789abc" not in data["masked_token"]
        assert "..." in data["masked_token"]


    async def test_rejects_invalid_provider(self, client):
        response = await client.put(
            "/admin/llm/config",
            json={
                "provider": "invalid_provider",
                "model_name": "invalid/model",
                "api_token": "some-token",
                "monthly_budget_usd": 50.0,
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == "VALIDATION_ERROR"


class TestGetLlmConfig:
    """Tests for GET /admin/llm/config."""

    async def test_returns_none_when_no_config(self, client):
        response = await client.get("/admin/llm/config")
        assert response.status_code == 200
        assert response.json() is None

    @patch("src.infrastructure.encryption.settings")
    async def test_returns_config_with_masked_token(self, mock_settings, client, db_session):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        mock_settings.llm_encryption_key = key

        # Create config via API
        await client.put(
            "/admin/llm/config",
            json={
                "provider": "gemini",
                "model_name": "gemini/gemini-2.0-flash",
                "api_token": "gemini-token-longvalue",
                "monthly_budget_usd": 30.0,
            },
        )

        response = await client.get("/admin/llm/config")
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "gemini"
        assert data["model_name"] == "gemini/gemini-2.0-flash"
        assert data["is_active"] is True
        # Full token must not appear
        assert "gemini-token-longvalue" not in data["masked_token"]


class TestGetLlmUsage:
    """Tests for GET /admin/llm/usage."""

    async def test_returns_empty_usage(self, client):
        response = await client.get("/admin/llm/usage")
        assert response.status_code == 200
        data = response.json()
        assert data["total_calls"] == 0
        assert data["total_cost_usd"] == 0.0


class TestPostLlmTest:
    """Tests for POST /admin/llm/test."""

    @patch("src.infrastructure.encryption.settings")
    @patch("src.infrastructure.llm_service.litellm")
    async def test_connection_test(self, mock_litellm, mock_enc_settings, client, db_session):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from cryptography.fernet import Fernet

        mock_enc_settings.llm_encryption_key = Fernet.generate_key().decode()

        # Create config first
        await client.put(
            "/admin/llm/config",
            json={
                "provider": "openai",
                "model_name": "openai/gpt-4o",
                "api_token": "sk-test-token-value",
                "monthly_budget_usd": 50.0,
            },
        )

        # Mock LiteLLM response
        usage = SimpleNamespace(prompt_tokens=5, completion_tokens=10)
        message = SimpleNamespace(content="Hello TaxPilot!")
        choice = SimpleNamespace(message=message)
        mock_response = MagicMock()
        mock_response.usage = usage
        mock_response.choices = [choice]
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)
        mock_litellm.completion_cost = MagicMock(return_value=0.0001)
        mock_litellm.enable_json_schema_validation = True

        response = await client.post("/admin/llm/test")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["response"] == "Hello TaxPilot!"
