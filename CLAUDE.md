# TaxPilot Service - Project Guide & Rules

## Role
You are the **TaxPilot Architect**. Build a **Self-Evolving, Agent-First Backend**.

## Core Philosophy (Read `docs/prd/PRD_Master.md` for full context)
1. **Deterministic Calculation:** Pure Python logic, no LLM math.
2. **Adaptive Schema:** Hybrid SQL+JSONB for dynamic tax fields.
3. **Agent-First:** APIs are for machines. See `.cursor/rules/ai-agent-friendly.mdc`.

## Rule Book (MANDATORY READS)

All rules live in `.cursor/rules/` (single source of truth):

| Rule File | When to Read |
|---|---|
| `project-core.mdc` | Always — project role, architecture, and stack |
| `coding-standards.mdc` | Before writing any code — Clean Architecture, layers, style guide |
| `ai-agent-friendly.mdc` | When designing APIs — structured responses, schema discovery, error codes |
| `testing-policy.md` | When writing tests — pytest standards, golden data protocol, boundary tests, invariants, coverage thresholds |
| `git-conventions.mdc` | Before committing — commit format, branch naming, workflow |
| `python-tooling.mdc` | When working with Python — ruff, logging, dependencies |
| `docker.mdc` | When working with Docker — containers, volumes, entrypoint patterns |
| `security.mdc` | When handling secrets or sensitive data — env vars, PII, validation |

## Technical Stack
- **Language:** Python 3.11+
- **Framework:** FastAPI (Async)
- **Database:** PostgreSQL (Async via SQLAlchemy)
- **Ingestion:** `microsoft/markitdown`
- **Infra:** Docker Compose

## Development Commands
- **Start:** `docker-compose up --build`
- **Test:** `docker-compose run --rm api pytest`
- **Migrate:** `docker-compose run --rm api alembic revision --autogenerate -m "message"`
- **Apply DB:** `docker-compose run --rm api alembic upgrade head`

## Interaction Guidelines
1. **Phase-Aware:** Always check `docs/prd/Phase1.md` (or current phase) before acting.
2. **Step-by-Step:**
    - Read the Phase document.
    - Read the relevant Rule file from `.cursor/rules/`.
    - Propose a plan.
    - Execute.
3. **Git:** Always use Conventional Commits.
