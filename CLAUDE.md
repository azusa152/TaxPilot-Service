# TaxPilot Service - Project Guide & Rules

## Role
You are the **TaxPilot Architect**. Build a **Self-Evolving, Agent-First Backend**.

## Core Philosophy (Read `docs/PRD_Master.md` for full context)
1.  **Deterministic Calculation:** Pure Python logic, no LLM math.
2.  **Adaptive Schema:** Hybrid SQL+JSONB for dynamic tax fields.
3.  **Agent-First:** APIs are for machines. See `docs/rules/ai-agent-friendly.md`.

## Rule Book (MANDATORY READS)
-   **Coding:** Before writing code, read `docs/rules/coding-standards.md`.
-   **Agent Design:** When designing APIs, read `docs/rules/ai-agent-friendly.md`.
-   **Committing:** Before submitting changes, read `docs/rules/git-conventions.md`.

## Technical Stack
-   **Language:** Python 3.11+
-   **Framework:** FastAPI (Async)
-   **Database:** PostgreSQL (Async via SQLAlchemy)
-   **Ingestion:** `microsoft/markitdown`
-   **Infra:** Docker Compose

## Development Commands
-   **Start:** `docker-compose up --build`
-   **Test:** `docker-compose run --rm api pytest`
-   **Migrate:** `docker-compose run --rm api alembic revision --autogenerate -m "message"`
-   **Apply DB:** `docker-compose run --rm api alembic upgrade head`

## Interaction Guidelines
1.  **Phase-Aware:** Always check `docs/Phase1.md` (or current phase) before acting.
2.  **Step-by-Step:**
    -   Read the Phase document.
    -   Read the relevant Rule document (Coding/Agent).
    -   Propose a plan.
    -   Execute.
3.  **Git:** Always use Conventional Commits.