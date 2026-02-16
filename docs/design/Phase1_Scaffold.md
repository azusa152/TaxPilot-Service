# Phase 1: Project Scaffold
**Goal:** Get `docker-compose up --build` running with a healthy FastAPI + PostgreSQL stack. Zero business logic — infrastructure only.

**Depends on:** Nothing (first phase)
**Produces:** Runnable Docker environment, health endpoint, project skeleton, dev tooling

---

## Context

We are starting from a completely greenfield state. This phase creates the foundational infrastructure that all subsequent phases build upon. Every file path, dependency, and convention established here sets the standard for the project.

**Architecture reference:** See `docs/design/TechDesign_Master.md` Section 2 for the full architecture overview.

---

## Tasks

### Task 1.1: Project Directory Structure

Create the Clean Architecture skeleton:

```
backend/
├── src/
│   ├── __init__.py
│   ├── main.py               # FastAPI app factory
│   ├── config.py             # pydantic-settings
│   ├── logging_config.py     # Centralized logger
│   ├── api/
│   │   ├── __init__.py
│   │   └── health_routes.py  # GET /health
│   ├── application/
│   │   └── __init__.py
│   ├── domain/
│   │   └── __init__.py
│   └── infrastructure/
│       └── __init__.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── api/
│       ├── __init__.py
│       └── test_health.py
├── Dockerfile
└── pyproject.toml
```

### Task 1.2: `backend/pyproject.toml`

```toml
[project]
name = "taxpilot-service"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.30",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.3.0",
    "markitdown>=0.1.0",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",
    "ruff>=0.5.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
target-version = "py311"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]
```

**Note:** Pin minimum versions, not exact versions. The lockfile (if used) handles reproducibility.

### Task 1.3: `backend/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir ".[dev]"

# Copy application code
COPY . .

# Run as non-root user
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

### Task 1.4: `docker-compose.yml` (project root)

```yaml
services:
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-taxpilot}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-taxpilot_dev}
      POSTGRES_DB: ${POSTGRES_DB:-taxpilot}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U taxpilot"]
      interval: 5s
      timeout: 3s
      retries: 5

  api:
    build:
      context: ./backend
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./backend:/app

volumes:
  pgdata:
```

### Task 1.5: `.env.example` (project root)

```env
# Database
DATABASE_URL=postgresql+asyncpg://taxpilot:taxpilot_dev@db:5432/taxpilot
POSTGRES_USER=taxpilot
POSTGRES_PASSWORD=taxpilot_dev
POSTGRES_DB=taxpilot

# Application
LOG_LEVEL=INFO
```

Copy to `.env` for local development: `cp .env.example .env`

### Task 1.6: `backend/src/config.py`

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://taxpilot:taxpilot_dev@db:5432/taxpilot"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
```

### Task 1.7: `backend/src/logging_config.py`

```python
import logging
import sys


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger
```

### Task 1.8: `backend/src/main.py`

```python
from fastapi import FastAPI

from src.api.health_routes import router as health_router
from src.logging_config import get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    application = FastAPI(
        title="TaxPilot Service",
        description="Self-Evolving, Agent-First Backend for Japanese Tax Calculation",
        version="0.1.0",
    )
    application.include_router(health_router)
    return application


app = create_app()

logger.info("TaxPilot Service started")
```

### Task 1.9: `backend/src/api/health_routes.py`

```python
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
```

### Task 1.10: `Makefile` (project root)

```makefile
.PHONY: start stop test lint format migrate help

start: ## Start all services
	docker-compose up --build

stop: ## Stop all services
	docker-compose down

test: ## Run tests
	docker-compose run --rm api pytest -v

lint: ## Lint code with ruff
	docker-compose run --rm api ruff check src/ tests/

format: ## Format code with ruff
	docker-compose run --rm api ruff format src/ tests/

migrate: ## Generate a new migration (usage: make migrate msg="description")
	docker-compose run --rm api alembic revision --autogenerate -m "$(msg)"

migrate-up: ## Apply all pending migrations
	docker-compose run --rm api alembic upgrade head

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
```

### Task 1.11: Test Setup

**`backend/tests/conftest.py`:**

```python
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

**`backend/tests/api/test_health.py`:**

```python
async def test_health_should_return_healthy_status(client):
    # Act
    response = await client.get("/health")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "database" in data
```

---

## Acceptance Criteria

1. `docker-compose up --build` starts both `db` and `api` services without errors.
2. `GET http://localhost:8000/health` returns `200` with `{"status": "healthy", "database": "not_configured"}`.
3. `GET http://localhost:8000/docs` shows Swagger UI with the health endpoint documented.
4. `make test` runs and `test_health.py` passes.
5. `make lint` runs without errors.
6. All files follow the directory structure defined in Task 1.1.
