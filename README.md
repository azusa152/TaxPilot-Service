# TaxPilot Service

Self-Evolving, Agent-First Backend for Japanese Tax Calculation.

TaxPilot is a deterministic tax logic engine consumed by external AI Agents and a Reference UI. It uses pure Python for all calculations (no LLM math) and an adaptive SQL+JSONB schema to handle evolving tax law fields without migrations.

## Tech Stack

- **Language:** Python 3.11+
- **Framework:** FastAPI (Async)
- **Database:** PostgreSQL 15+ (SQLAlchemy 2.0 Async + Alembic)
- **Ingestion:** microsoft/markitdown
- **Containerization:** Docker Compose

## Prerequisites

- Docker and Docker Compose

## Quick Start

```bash
# Copy environment variables
cp .env.example .env

# Start all services (FastAPI + PostgreSQL + Admin Dashboard)
make start

# In a separate terminal — apply database migrations
make migrate-up

# Verify
curl http://localhost:8000/health
```

## Configuration

All ports are configurable via `.env` to avoid conflicts when running alongside other services:

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_PORT` | `5432` | Host port for PostgreSQL |
| `API_PORT` | `8000` | Host port for FastAPI |
| `ADMIN_PORT` | `8501` | Host port for Streamlit admin dashboard |

## Development Commands

| Command | Description |
|---|---|
| `make start` | Start all services (`docker-compose up --build`) |
| `make stop` | Stop all services |
| `make test` | Run test suite |
| `make lint` | Lint with ruff |
| `make format` | Format with ruff |
| `make migrate msg="description"` | Generate Alembic migration |
| `make migrate-up` | Apply pending migrations |

## Project Structure

```
backend/src/
├── api/              # FastAPI route handlers (thin controllers)
├── application/      # Use-case orchestration (services)
├── domain/           # Pure business rules (no framework imports)
├── infrastructure/   # External adapters (DB, file parsers)
├── config.py         # pydantic-settings configuration
├── logging_config.py # Centralized logging
└── main.py           # FastAPI app factory
```

## Testing & Quality Assurance

TaxPilot follows a **"Zero Tolerance for Math Errors"** policy. Tax calculations are deterministic — all JPY amounts use exact integer assertions, never floating-point approximations.

### Test Pyramid

| Layer | Target | Coverage |
|-------|--------|----------|
| **Unit** | `domain/tax_calculations.py` — pure functions | >= 95% branch |
| **Service** | `application/` — orchestration | Mocked DB |
| **Integration** | `api/` — HTTP + DB round-trip | All status codes |
| **Golden Data** | NTA-verified input/output pairs | 100% pass rate |

### Golden Data Protocol

Expected tax values are verified against **official government tools** (NTA Kakutei Shinkoku Corner, MIC Furusato Simulation), not invented. Golden data files in `backend/tests/golden_data/` include full traceability: tax year, oracle source, verification date, and law references.

### Run Tests

```bash
# Run all tests
make test

# Run with coverage
docker-compose run --rm api pytest --cov=src --cov-branch

# Run domain tests only (tax logic)
docker-compose run --rm api pytest tests/domain/ -v
```

See [.cursor/rules/testing-policy.md](.cursor/rules/testing-policy.md) for the full testing policy.

## Architecture

Clean Architecture with strict layer separation:

```
api/ → application/ → domain/
          ↓
     infrastructure/ → domain/
```

See [docs/design/TechDesign_Master.md](docs/design/TechDesign_Master.md) for full technical design.
