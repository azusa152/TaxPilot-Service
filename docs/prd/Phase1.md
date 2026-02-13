# Phase 1: Data Foundation & Infrastructure
**Goal:** Establish the database schema, ORM models, and basic ingestion infrastructure. No business logic yet.

## Context
We are building the **Data Layer** for TaxPilot. We need to handle both structured relational data and unstructured document ingestion using **Microsoft MarkItDown**.

## Tasks Breakdown

### Task 1.1: Project Initialization
* Setup a Python 3.11 project structure.
* Create `requirements.txt` or `pyproject.toml` including:
    * `fastapi`, `uvicorn`, `sqlalchemy`, `asyncpg`, `alembic`, `pydantic-settings`.
    * **`markitdown`**: For document ingestion.
* Create `docker-compose.yml` containing:
    * `db`: PostgreSQL 15+ (Alpine) - *Essential for robust JSONB support.*
    * `api`: Python container (FastAPI).
* Configure environment variables (`.env`) for DB credentials and LLM keys (if MarkItDown needs Vision).

### Task 2.1: Database Models (SQLAlchemy)
Create `src/models.py`. Implement the following models using SQLAlchemy 2.0 style (Mapped/mapped_column):

1.  **User**: `id` (PK, String), `created_at`.
2.  **IncomeEntry**:
    * `user_id` (FK).
    * `payment_date` (Date).
    * `income_type` (Enum: SALARY, BONUS, OTHER).
    * `gross_amount` (Int), `social_insurance` (Int), `withholding_tax` (Int), `resident_tax` (Int).
    * `raw_content` (Text/LargeBinary): Stores the **Markdown output** from MarkItDown.
3.  **TaxProfile**:
    * `user_id` (FK), `year` (Int) -> Composite Index.
    * **Core Columns:** `has_spouse` (Bool), `dependents_count` (Int), `social_insurance_premium` (Int), `life_insurance_premium` (Int), `ideco_monthly_contribution` (Int).
    * **Dynamic Column:** `additional_attributes` (JSON/JSONB). **Critical:** This stores the adaptive data.
4.  **ProfileDefinition**:
    * `year` (Int, PK).
    * `schema_definition` (JSON/JSONB). Stores the UI/Agent field requirements.
5.  **AlgorithmRegistry**:
    * `function_name` (String), `version` (String).
    * `code_content` (Text), `status` (Enum: DRAFT, ACTIVE, ARCHIVED).

### Task 3.1: API Schemas (Pydantic v2)
Create `src/schemas.py`. Implement Request/Response models:

* `IncomeEntryCreate` / `IncomeEntryResponse`.
* `TaxProfileUpdate` / `TaxProfileResponse`:
    * Ensure `additional_attributes` is typed as `Dict[str, Any]`.
* `ProfileDefinitionResponse`.

### Task 4.1: Database Infrastructure
* Create `src/database.py`: Setup `AsyncSession` and `create_async_engine`.
* Setup **Alembic** for migrations (`alembic init -t async`).
* Generate the initial migration script (`alembic revision --autogenerate`).

### Task 5.1: Ingestion Infrastructure
* Create `src/ingestion.py`.
* Implement a `DocumentIngestor` class utilizing **MarkItDown**.
* Method `convert_to_markdown(file_path: str) -> str`:
    * Accepts a file path (PDF/Image).
    * Returns the Markdown text content preserving table structures.
    * *Note: This is a utility for future phases, but setting it up now ensures dependencies work.*

## Acceptance Criteria
1.  `docker-compose up` starts successfully.
2.  The API connects to the PostgreSQL database without error.
3.  The migration script runs and creates all 5 tables in the DB.
4.  `TaxProfile` table has a working JSONB column.
5.  `markitdown` is installed and can be imported in the Python environment.