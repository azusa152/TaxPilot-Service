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

# Start all services (FastAPI + PostgreSQL)
make start

# Verify
curl http://localhost:8000/health
```

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

## Architecture

Clean Architecture with strict layer separation:

```
api/ → application/ → domain/
          ↓
     infrastructure/ → domain/
```

See [docs/design/TechDesign_Master.md](docs/design/TechDesign_Master.md) for full technical design.
