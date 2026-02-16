# TaxPilot Service

Self-Evolving, Agent-First Backend for Japanese Tax Calculation.

TaxPilot is a deterministic tax logic engine consumed by external AI Agents and a Reference UI. It uses pure Python for all calculations (no LLM math) and an adaptive SQL+JSONB schema to handle evolving tax law fields without migrations.

## Tech Stack

### Backend
- **Language:** Python 3.11+
- **Framework:** FastAPI (Async)
- **Database:** PostgreSQL 15+ (SQLAlchemy 2.0 Async + Alembic)
- **Ingestion:** microsoft/markitdown
- **LLM Integration:** LiteLLM (multi-provider), RestrictedPython (code sandbox)
- **Web Crawling:** Crawl4AI (async, AI-optimized)
- **Notifications:** aiosmtplib (async SMTP)
- **Scheduling:** APScheduler
- **Encryption:** cryptography (Fernet)

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

## Evolution Loop (Self-Evolving Tax Logic)

TaxPilot includes a **self-evolving pipeline** that monitors Japanese tax law changes and automatically generates updated calculation formulas for admin review. The system is built as a series of composable phases:

| Phase | Component | Description |
|-------|-----------|-------------|
| 6-Pre | **Bootstrap & Verification** | Cold-start: seeds the AlgorithmRegistry with existing formulas, crawls baseline NTA pages, and uses LLM to verify formula accuracy |
| 6A | **LLM Gateway** | Unified LLM access via LiteLLM (OpenAI, Gemini, Claude). API tokens encrypted at rest with Fernet. Budget tracking and structured output via Pydantic |
| 6B | **NTA Crawler** | Async crawler (Crawl4AI) monitors National Tax Agency pages for content changes. Stores parsed Markdown snapshots with content hashing for change detection |
| 6C | **Regulation Parser** | LLM-powered analysis of NTA content diffs to identify specific law changes (thresholds, rates, brackets, new deductions) |
| 6D | **Code & Schema Generator** | Generates updated Python calculation functions and ProfileDefinition schema proposals from parsed law changes. Code validated via RestrictedPython sandbox |
| 6E | **Pipeline Orchestration & Admin Review** | End-to-end workflow from detection to activation. 4-option admin review: Accept, Modify, Regenerate (with hints), or Skip. Rollback support and audit logging |
| 6F | **Email Notifications** | Pluggable notification system (SMTP for MVP). Alerts admin on regulation changes, formulas ready for review, activations, failures, and weekly deferred reminders |

Design documents: [docs/design/evolution-loop/](docs/design/evolution-loop/)

### Evolution Loop Configuration

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `openai` | LLM provider (openai, gemini, claude) |
| `LLM_MODEL` | `openai/gpt-4o` | LiteLLM model identifier |
| `LLM_API_TOKEN` | *(empty)* | LLM API key (encrypted at rest) |
| `LLM_ENCRYPTION_KEY` | *(empty)* | Fernet key for encrypting secrets |
| `LLM_MONTHLY_BUDGET_USD` | `50.00` | Monthly LLM spending limit |
| `NTA_CRAWL_INTERVAL_HOURS` | `24` | Hours between NTA crawl cycles |
| `NTA_CRAWL_RATE_LIMIT_SECONDS` | `2` | Delay between page fetches |

SMTP notifications are configured via the admin dashboard (`PUT /admin/notifications/config`) or the Streamlit UI. SMTP passwords are encrypted using the same Fernet key as LLM tokens.

### Notification Events

| Event | Trigger | Priority |
|-------|---------|----------|
| `REGULATION_CHANGE_DETECTED` | NTA crawler detects a page change | High (retry) |
| `FORMULA_READY_FOR_REVIEW` | Pipeline generates code, enters awaiting review | High (retry) |
| `FORMULA_ACTIVATED` | Admin accepts/modifies and activates a formula | Medium |
| `FORMULA_REGENERATING` | Admin requests LLM regeneration | Low |
| `RUN_FAILED` | Pipeline fails at any step | High (retry) |
| `DEFERRED_REMINDER` | Weekly digest of deferred regulation updates | Medium |

### Evolution Loop API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/admin/evolution/run` | Trigger a new evolution pipeline run |
| `GET` | `/admin/evolution/runs` | List evolution runs with filters |
| `GET` | `/admin/evolution/runs/{id}` | Get detailed run information |
| `POST` | `/admin/evolution/runs/{id}/review` | Submit admin review decision |
| `POST` | `/admin/evolution/runs/{id}/rollback` | Rollback to previous algorithm version |
| `POST` | `/admin/notifications/config` | Create or update SMTP notification config |
| `GET` | `/admin/notifications/config` | Get active notification config (password masked) |
| `DELETE` | `/admin/notifications/config` | Disable notification config |
| `GET` | `/admin/notifications/logs` | List notification history with filters |
| `GET` | `/admin/notifications/logs/stats` | Get notification delivery statistics |

## Architecture

Clean Architecture with strict layer separation:

```
api/ → application/ → domain/
          ↓
     infrastructure/ → domain/
```

See [docs/design/TechDesign_Master.md](docs/design/TechDesign_Master.md) for full technical design.
