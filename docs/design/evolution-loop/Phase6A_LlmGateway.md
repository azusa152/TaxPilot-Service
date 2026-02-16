# Phase 6A: LLM Gateway

**Goal:** Build the LLM integration layer using **LiteLLM** as the provider abstraction, with encrypted token management, cost tracking, and admin configuration via Streamlit.

**Depends on:** Phase 5 (existing infrastructure layer)
**Produces:** `LlmService` wrapper around LiteLLM, encrypted token storage, Streamlit config page, health-check endpoint, usage/cost tracking

---

## Context

The Evolution Loop requires LLM capabilities for:
1. **Regulation parsing** (Phase 6C) — analyzing NTA text to identify law changes
2. **Code generation** (Phase 6D) — generating updated Python calculation functions
3. **Schema generation** (Phase 6D) — determining new user input fields
4. **Bootstrap verification** (Phase 6-Pre) — verifying existing formulas against NTA text

Instead of building custom adapters for each LLM provider, we use **LiteLLM** (MIT license, v1.81+) — the industry-standard Python library for multi-provider LLM access. It provides a unified OpenAI-compatible interface to 100+ providers via a single `completion()` call.

**Key LiteLLM features we leverage:**

- Unified `completion(model="provider/model", messages=...)` call
- All responses in the same OpenAI-compatible format
- Built-in cost tracking per call (`response._hidden_params["response_cost"]`)
- Provider errors mapped to consistent exception types
- Retry logic and streaming support built-in
- Pydantic `response_format` for structured output (used heavily in Phases 6C and 6D)

**LiteLLM model strings:**

| Provider | Model String | Notes |
|----------|-------------|-------|
| Gemini | `gemini/gemini-2.0-flash` | Fast, cost-effective |
| Gemini | `gemini/gemini-1.5-pro` | Higher quality |
| OpenAI | `openai/gpt-4o` | Best general-purpose |
| OpenAI | `openai/gpt-4-turbo` | Balanced cost/quality |
| Claude | `anthropic/claude-3-5-sonnet-20241022` | Strong reasoning |
| Claude | `anthropic/claude-3-haiku-20240307` | Fast, low cost |

---

## Tasks

### Task 6A.1: Dependencies

**File:** `backend/pyproject.toml`

Add dependencies:

```toml
[project]
dependencies = [
    # ... existing deps ...
    "litellm>=1.81.0",
    "cryptography>=42.0.0",
]
```

### Task 6A.2: Enums

**File:** `backend/src/domain/enums.py`

```python
class LlmProvider(str, Enum):
    """Supported LLM providers."""
    GEMINI = "gemini"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
```

### Task 6A.3: Database Models

**File:** `backend/src/infrastructure/models.py`

Add two new tables:

```python
class LlmProviderConfig(Base):
    """Stores LLM provider configuration with encrypted API tokens."""
    __tablename__ = "llm_provider_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    encrypted_api_token: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    monthly_budget_usd: Mapped[float] = mapped_column(
        Numeric(10, 2), default=50.00
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LlmUsageLog(Base):
    """Tracks token usage and cost for each LLM call."""
    __tablename__ = "llm_usage_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=True)
    evolution_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("evolution_runs.id"), nullable=True
    )
    caller: Mapped[str] = mapped_column(
        String(100), nullable=True
    )  # e.g., "regulation_parser", "code_generator"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_llm_usage_logs_created_at", "created_at"),
        Index("ix_llm_usage_logs_evolution_run_id", "evolution_run_id"),
    )
```

### Task 6A.4: Pydantic Schemas

**File:** `backend/src/domain/schemas.py`

```python
class LlmConfigCreate(BaseModel):
    """Request schema for creating/updating LLM provider configuration."""
    provider: str = Field(
        description="LLM provider name (gemini, openai, anthropic)"
    )
    model_name: str = Field(
        description="LiteLLM model string (e.g., 'openai/gpt-4o')"
    )
    api_token: str = Field(
        description="API token for the provider (will be encrypted at rest)"
    )
    monthly_budget_usd: float = Field(
        default=50.00,
        description="Monthly budget cap in USD. Calls are rejected when exceeded."
    )


class LlmConfigResponse(BaseModel):
    """Response schema for LLM provider configuration (token masked)."""
    id: int = Field(description="Config ID")
    provider: str = Field(description="LLM provider name")
    model_name: str = Field(description="LiteLLM model string")
    masked_token: str = Field(
        description="Masked API token (e.g., 'sk-...a3f2')"
    )
    is_active: bool = Field(description="Whether this config is the active one")
    monthly_budget_usd: float = Field(description="Monthly budget cap in USD")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LlmUsageSummary(BaseModel):
    """Summary of LLM usage and costs."""
    total_calls: int = Field(description="Total number of LLM calls")
    total_prompt_tokens: int = Field(description="Total prompt tokens used")
    total_completion_tokens: int = Field(description="Total completion tokens used")
    total_cost_usd: float = Field(description="Total cost in USD")
    daily_breakdown: list[dict] = Field(
        description="Cost breakdown by day [{date, calls, cost_usd}]"
    )
    monthly_total_usd: float = Field(
        description="Total cost for the current month"
    )
    budget_remaining_usd: float = Field(
        description="Remaining budget for the current month"
    )
```

### Task 6A.5: Configuration

**File:** `backend/src/config.py`

Add new fields to the existing `Settings(BaseSettings)` class (per project convention — all config via `pydantic-settings`):

```python
class Settings(BaseSettings):
    # ... existing fields ...

    # LLM Gateway (Phase 6A)
    llm_provider: str = "openai"
    llm_model: str = "openai/gpt-4o"
    llm_api_token: str = ""
    llm_encryption_key: str = ""
    llm_monthly_budget_usd: float = 50.00

    model_config = SettingsConfigDict(env_file=".env")
```

Access via `settings.llm_model` etc. — never use bare `os.getenv()` (per `security.mdc`).

### Task 6A.6a: Encryption Utilities (Infrastructure Layer)

**File:** `backend/src/infrastructure/encryption.py`

Shared encryption utilities used by both LLM config and notification config. Lives in **infrastructure/** (not application/) so that other infrastructure modules can import it without violating Clean Architecture layer boundaries.

```python
"""Shared Fernet encryption utilities for secrets at rest.

Used for LLM API tokens (Phase 6A) and SMTP passwords (Phase 6F).
"""
from cryptography.fernet import Fernet

from src.config import get_settings
from src.logging_config import get_logger

logger = get_logger(__name__)


def _get_fernet() -> Fernet:
    """Get Fernet instance for token encryption/decryption."""
    settings = get_settings()
    if not settings.llm_encryption_key:
        raise ValueError(
            "LLM_ENCRYPTION_KEY is not set. Generate one with: "
            "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    return Fernet(settings.llm_encryption_key.encode())


def encrypt_token(token: str) -> str:
    """Encrypt an API token for storage."""
    return _get_fernet().encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt an API token for use."""
    return _get_fernet().decrypt(encrypted.encode()).decode()


def mask_token(token: str) -> str:
    """Mask a token for display (e.g., 'sk-...a3f2')."""
    if len(token) <= 8:
        return "****"
    return f"{token[:3]}...{token[-4:]}"
```

### Task 6A.6b: LLM Config Service (Application Layer)

**File:** `backend/src/application/llm_config_service.py`

Handles CRUD for provider config and usage queries. Encryption/decryption is delegated to `infrastructure/encryption.py`.

```python
from sqlalchemy import select, func as sqla_func
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.schemas import LlmConfigCreate, LlmConfigResponse, LlmUsageSummary
from src.infrastructure.encryption import encrypt_token, decrypt_token, mask_token
from src.infrastructure.models import LlmProviderConfig, LlmUsageLog
from src.logging_config import get_logger

logger = get_logger(__name__)


async def upsert_llm_config(
    db: AsyncSession, data: LlmConfigCreate
) -> LlmConfigResponse:
    """Create or update the LLM provider configuration."""
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
    """Get the active LLM provider config (with encrypted token)."""
    result = await db.execute(
        select(LlmProviderConfig).where(LlmProviderConfig.is_active == True)
    )
    return result.scalar_one_or_none()


async def get_decrypted_token(db: AsyncSession) -> tuple[str, str] | None:
    """Get the active model string and decrypted API token.

    Returns (model_name, api_token) or None if no config exists.
    """
    config = await get_active_config(db)
    if config is None:
        return None
    return config.model_name, decrypt_token(config.encrypted_api_token)


async def get_usage_summary(db: AsyncSession) -> LlmUsageSummary:
    """Get LLM usage summary for the current month."""
    # ... query LlmUsageLog grouped by day for current month
    # ... compute totals and budget remaining
    pass
```

### Task 6A.7: LLM Service (Infrastructure Layer)

**File:** `backend/src/infrastructure/llm_service.py`

The core service that wraps LiteLLM and provides a clean interface for all LLM interactions.

```python
import litellm
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.llm_config_service import get_active_config
from src.config import get_settings
from src.infrastructure.encryption import decrypt_token
from src.infrastructure.models import LlmUsageLog
from src.logging_config import get_logger

logger = get_logger(__name__)

# Enable client-side JSON schema validation as fallback
litellm.enable_json_schema_validation = True

# IMPORTANT: Use litellm.acompletion() (async) — NOT litellm.completion() (sync).
# completion() blocks the FastAPI event loop. acompletion() is the async equivalent.


class LlmService:
    """Wrapper around LiteLLM for multi-provider LLM access.

    Reads config from DB (preferred) or falls back to env vars.
    Logs usage and cost. Enforces monthly budget cap.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_config(self) -> tuple[str, str, float]:
        """Get model, token, and budget from DB or env vars.

        Returns: (model_name, api_token, monthly_budget_usd)
        """
        config = await get_active_config(self.db)
        if config:
            token = decrypt_token(config.encrypted_api_token)
            return config.model_name, token, float(config.monthly_budget_usd)
        # Fallback to pydantic-settings
        settings = get_settings()
        return settings.llm_model, settings.llm_api_token, settings.llm_monthly_budget_usd

    async def _check_budget(self, budget: float) -> None:
        """Check if monthly budget is exceeded. Raises if exceeded."""
        # Query current month's total cost from LlmUsageLog
        # Raise ValueError if total >= budget
        pass

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
        """Log LLM usage to the database."""
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
            messages: Chat messages in OpenAI format [{"role": ..., "content": ...}]
            caller: Identifier for the calling component (for usage tracking)
            evolution_run_id: Optional link to an evolution run

        Returns:
            The LLM's text response.

        Raises:
            ValueError: If monthly budget is exceeded.
        """
        model, token, budget = await self._get_config()
        await self._check_budget(budget)

        # Set the API key for the provider
        provider = model.split("/")[0] if "/" in model else "openai"
        litellm.api_key = token

        # Use acompletion() — the async variant — to avoid blocking the event loop
        response = await litellm.acompletion(model=model, messages=messages)

        # Extract usage and cost
        usage = response.usage
        cost = response._hidden_params.get("response_cost", 0.0)

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
            messages: Chat messages in OpenAI format
            response_format: Pydantic model class for response validation
            caller: Identifier for the calling component
            evolution_run_id: Optional link to an evolution run

        Returns:
            Validated Pydantic model instance.
        """
        model, token, budget = await self._get_config()
        await self._check_budget(budget)

        provider = model.split("/")[0] if "/" in model else "openai"
        litellm.api_key = token

        # Use acompletion() — the async variant — to avoid blocking the event loop
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            response_format=response_format,
        )

        usage = response.usage
        cost = response._hidden_params.get("response_cost", 0.0)

        await self._log_usage(
            provider=provider,
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cost_usd=cost,
            caller=caller,
            evolution_run_id=evolution_run_id,
        )

        # Validate the response against the Pydantic model
        result = response_format.model_validate_json(
            response.choices[0].message.content
        )

        logger.info(
            f"LLM structured call: model={model}, format={response_format.__name__}, "
            f"tokens={usage.prompt_tokens}+{usage.completion_tokens}, cost=${cost:.4f}"
        )
        return result

    async def test_connection(self) -> dict:
        """Test the LLM connection with a simple prompt.

        Returns: dict with model, response text, cost, and latency.
        """
        import time

        start = time.time()
        response_text = await self.generate(
            messages=[{"role": "user", "content": "Say 'Hello TaxPilot' in one sentence."}],
            caller="connection_test",
        )
        elapsed = time.time() - start

        model, _, _ = await self._get_config()
        return {
            "model": model,
            "response": response_text,
            "latency_seconds": round(elapsed, 2),
            "status": "ok",
        }
```

### Task 6A.8: API Routes

**File:** `backend/src/api/llm_config_routes.py`

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.llm_config_service import (
    get_active_config,
    get_usage_summary,
    upsert_llm_config,
)
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
async def put_llm_config(
    data: LlmConfigCreate, db: AsyncSession = Depends(get_db)
):
    return await upsert_llm_config(db, data)


@router.get(
    "/config",
    response_model=LlmConfigResponse | None,
    summary="Get current LLM provider configuration (token masked)",
)
async def get_llm_config(db: AsyncSession = Depends(get_db)):
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
    service = LlmService(db)
    return await service.test_connection()


@router.get(
    "/usage",
    response_model=LlmUsageSummary,
    summary="Get LLM usage and cost summary for the current month",
)
async def get_llm_usage(db: AsyncSession = Depends(get_db)):
    return await get_usage_summary(db)
```

**Update `backend/src/main.py`:**

```python
from src.api.llm_config_routes import router as llm_config_router

# Inside create_app():
application.include_router(llm_config_router)
```

### Task 6A.9: Streamlit Admin Page — LLM Configuration

**File:** `admin/app.py` (new page or section)

The Streamlit "LLM Configuration" page provides:

1. **Provider Selection:**
   - Dropdown: Gemini / OpenAI / Claude
   - Model string input (with suggestions based on selected provider)
   - API token input (password field)
   - Monthly budget cap input (number)
   - Save button → calls `PUT /admin/llm/config`

2. **Test Connection:**
   - "Test Connection" button → calls `POST /admin/llm/test`
   - Shows: response text, latency, cost of the test call
   - Green/red status indicator

3. **Usage Dashboard:**
   - Current month cost vs budget (progress bar)
   - Daily cost chart (bar chart)
   - Per-run cost breakdown table
   - Total tokens used (prompt + completion)

### Task 6A.10: Alembic Migration

Create an Alembic migration for the new tables:

```bash
alembic revision --autogenerate -m "add llm_provider_configs and llm_usage_logs tables"
```

### Task 6A.11: Environment Variables

**File:** `.env.example`

Add:

```bash
# LLM Gateway (Phase 6A)
LLM_PROVIDER=openai
LLM_MODEL=openai/gpt-4o
LLM_API_TOKEN=
LLM_ENCRYPTION_KEY=
LLM_MONTHLY_BUDGET_USD=50.00
```

---

## Security

- **Token encrypted at rest** via Fernet (`cryptography` library); decrypted only in-memory during LLM calls
- **Token never logged**, never returned in full via API (masked: `sk-...a3f2`)
- `LLM_ENCRYPTION_KEY` loaded from env, never hardcoded
- Streamlit config page behind admin password
- **Budget enforcement:** `LlmService` checks monthly spend before each call and rejects if budget exceeded
- **Usage logging:** Every LLM call is logged with token counts and cost for audit

---

## Test Specification

Per `testing-policy.md`, every task must ship with tests. The following tests mirror the source layout in `backend/tests/`.

### Unit Tests (`tests/infrastructure/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_encryption.py` | `encryption.py` | encrypt/decrypt round-trip, invalid key raises `ValueError`, mask_token edge cases (short/long) |
| `test_llm_service.py` | `LlmService` | generate() returns text (mock `acompletion`), generate_structured() returns validated Pydantic model, budget exceeded raises error, usage logged to DB |

### Unit Tests (`tests/application/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_llm_config_service.py` | `llm_config_service` | upsert creates new config, upsert updates existing config, get_active_config returns None when empty, get_usage_summary aggregation |

### Integration Tests (`tests/api/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_llm_config_routes.py` | API endpoints | `PUT /admin/llm/config` stores encrypted token and returns masked, `GET /admin/llm/config` returns config or 404, `POST /admin/llm/test` validates connection (mock LLM), `GET /admin/llm/usage` returns summary |

### Test Conventions
- Use `pytest-asyncio` for all async tests.
- Mock `litellm.acompletion` — never make real LLM calls in tests.
- Use factory fixtures for `LlmProviderConfig` and `LlmUsageLog` records.
- Exact integer assertions for budget calculations (JPY precision).

---

## Acceptance Criteria

1. Admin can select provider + model and enter token via Streamlit UI or env vars.
2. `LlmService.generate(messages)` calls the selected provider via LiteLLM and returns text.
3. `LlmService.generate_structured(messages, response_format)` returns a validated Pydantic model.
4. Token is stored encrypted in DB; `GET /admin/llm/config` returns masked token.
5. Test connection button validates the token works and shows cost.
6. Each LLM call logs token usage and cost to `LlmUsageLog`.
7. Budget cap is enforced; calls are rejected with a clear error when budget is exceeded.
8. Usage dashboard shows daily/monthly cost breakdown.
