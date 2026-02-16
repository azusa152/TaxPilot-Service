# TaxPilot Service

Self-Evolving, Agent-First Backend for Japanese Tax Calculation.

TaxPilot is a deterministic tax logic engine consumed by external AI Agents and a Reference UI. It uses pure Python for all calculations (no LLM math) and an adaptive SQL+JSONB schema to handle evolving tax law fields without migrations.

## Tech Stack

### Backend
- **Language:** Python 3.11+
- **Framework:** FastAPI (Async)
- **Database:** PostgreSQL 15+ (SQLAlchemy 2.0 Async + Alembic)
- **Ingestion:** microsoft/markitdown

### Frontend
- **Framework:** Next.js 14 (App Router)
- **Language:** TypeScript
- **Styling:** Tailwind CSS with CSS variable theming (light/dark)
- **i18n:** next-intl (Japanese, English, Traditional Chinese)
- **Icons:** Lucide React

### Infrastructure
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
| `FRONTEND_PORT` | `3000` | Host port for Next.js frontend |

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
| `make frontend-dev` | Start frontend in dev mode (port 3000) |
| `make frontend-build` | Build frontend production bundle |

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

frontend/
├── src/
│   ├── app/[locale]/     # Next.js App Router pages (i18n routing)
│   ├── components/
│   │   ├── layout/       # Header, Sidebar, Footer, MobileNav
│   │   ├── shared/       # Reusable components (DataTable, FormField, etc.)
│   │   └── ui/           # Primitives (Skeleton, ToastContainer)
│   ├── lib/              # API client, utilities, context providers
│   └── i18n/             # Routing and navigation config
├── messages/             # Translation files (en.json, ja.json, zh-TW.json)
└── package.json
```

### Frontend Architecture

The frontend is a Next.js 14 App Router application with locale-prefix routing (`/ja/...`, `/en/...`, `/zh-TW/...`). Client-side components call the backend through a Next.js catch-all API route handler (`/api/[...path]`) that proxies requests to the FastAPI backend, avoiding CORS issues and Docker hostname resolution problems in the browser.

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
