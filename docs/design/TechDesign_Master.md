# TaxPilot Service — Technical Design Document
**Version:** 1.0
**Status:** Active
**PRD Reference:** `docs/prd/PRD_Master.md`

---

## 1. Overview

TaxPilot is a **Self-Evolving, Agent-First Backend Service** for Japanese tax calculation. It serves as a deterministic "Tax Logic Engine" consumed by external AI Agents (e.g., OpenClaw) and a Reference UI.

This document defines the technical architecture, data model, API surface, and implementation phases. Individual phase documents contain the detailed task breakdowns for Cursor-driven development.

---

## 2. System Architecture

### 2.1 Dual-Loop Design

```
┌─────────────────────────────────────────────────────────┐
│                    SERVICE LOOP (Fast)                   │
│                                                         │
│  Agent/UI ──► FastAPI ──► Application Services           │
│                              │           │              │
│                         Domain Logic   Infrastructure    │
│                         (Pure Python)  (PostgreSQL,      │
│                                        MarkItDown)       │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                   EVOLUTION LOOP (Slow)                  │
│                                                         │
│  NTA Crawler ──► LLM Code Generator ──► Admin Review     │
│                                          (Streamlit)     │
│                                              │          │
│                                       Hot-Reload ──► AlgorithmRegistry │
└─────────────────────────────────────────────────────────┘
```

**Service Loop** handles all runtime requests: document ingestion, tax profile management, and deterministic calculations. It is fast, stable, and fully testable.

**Evolution Loop** handles law changes: NTA website monitoring, LLM-assisted code generation, and human-approved hot-reloading of calculation algorithms. It is slow, safe, and admin-gated.

### 2.2 Clean Architecture Layers

All backend code lives under `backend/src/` with strict layer separation:

```
backend/src/
├── api/                  # FastAPI route handlers (thin controllers)
│   ├── health_routes.py
│   ├── user_routes.py
│   ├── income_routes.py
│   ├── profile_routes.py
│   ├── ingestion_routes.py
│   └── tax_routes.py
├── application/          # Use-case orchestration (services)
│   ├── user_service.py
│   ├── income_service.py
│   ├── profile_service.py
│   ├── ingestion_service.py
│   ├── tax_service.py
│   └── algorithm_service.py
├── domain/               # Pure business rules (zero framework imports)
│   ├── enums.py
│   ├── constants.py
│   ├── schemas.py        # Pydantic v2 request/response models
│   └── tax_calculations.py
├── infrastructure/       # External adapters
│   ├── database.py       # AsyncSession factory, engine
│   ├── models.py         # SQLAlchemy ORM models
│   ├── markitdown_adapter.py
│   └── algorithm_loader.py
├── config.py             # pydantic-settings configuration
├── logging_config.py     # Centralized logging setup
└── main.py               # FastAPI app factory
```

### 2.3 Dependency Rules

```
api/ ──────► application/ ──────► domain/
                  │
             infrastructure/ ────► domain/
```

- `domain/` imports **nothing** from other layers or frameworks (except Pydantic for schemas).
- `application/` imports from `domain/` only. Receives infrastructure via dependency injection.
- `infrastructure/` imports from `domain/` and `config`. Implements repository interfaces.
- `api/` imports from `application/` and wires dependencies via `Depends()`.

---

## 3. Data Model

### 3.1 Entity Relationship Diagram

```
┌──────────┐       ┌───────────────┐       ┌──────────────┐
│   User   │──1:N──│  IncomeEntry  │       │  ProfileDef  │
│──────────│       │───────────────│       │──────────────│
│ id (PK)  │       │ id (PK)       │       │ year (PK)    │
│ display_ │       │ user_id (FK)  │       │ schema_def   │
│   name   │       │ payment_date  │       │   (JSONB)    │
│ created_ │       │ income_type   │       │ created_at   │
│   at     │       │ gross_amount  │       └──────────────┘
└──────────┘       │ social_ins    │
     │             │ withholding   │       ┌──────────────┐
     │             │ resident_tax  │       │ AlgorithmReg │
     │             │ source_file   │       │──────────────│
     │             │ raw_content   │       │ id (PK)      │
     │             │ created_at    │       │ function_name│
     │             └───────────────┘       │ version      │
     │                                     │ code_content │
     │             ┌───────────────┐       │ status       │
     └──────1:N────│  TaxProfile   │       │ source_law_  │
                   │───────────────│       │   hash       │
                   │ id (PK)       │       │ created_at   │
                   │ user_id (FK)  │       └──────────────┘
                   │ year          │
                   │ has_spouse    │
                   │ dependents_   │
                   │   count       │
                   │ social_ins_   │
                   │   premium     │
                   │ life_ins_     │
                   │   premium     │
                   │ ideco_monthly │
                   │ additional_   │
                   │   attributes  │
                   │   (JSONB)     │
                   │ created_at    │
                   └───────────────┘
```

### 3.2 Key Design Decisions

| Entity | Decision | Rationale |
|---|---|---|
| **TaxProfile** | Core fields as SQL columns + `additional_attributes` JSONB | Stable fields (spouse, dependents) get column-level indexing. Year-specific fields (fixed tax cut, GPU deduction) live in JSONB to avoid annual migrations. |
| **ProfileDefinition** | `schema_definition` JSONB per year | Agents call `GET /profile-definition/{year}` to discover what fields to collect. New tax years require only a new row, not a schema change. |
| **AlgorithmRegistry** | Stores Python source code as text | Enables versioning, rollback, and hot-reload without redeployment. `status` enum gates which version is active. |
| **IncomeEntry** | `raw_content` stores MarkItDown Markdown | Preserves the original parsed document for audit trail and re-parsing if extraction logic improves. |
| **User** | `id` is String (UUID) | Allows external systems (Agents) to generate IDs. No auto-increment dependency. |

### 3.3 Indexes

| Table | Index | Type |
|---|---|---|
| `income_entries` | `(user_id, payment_date)` | Composite |
| `tax_profiles` | `(user_id, year)` | Unique Composite |
| `algorithm_registry` | `(function_name, version)` | Unique Composite |
| `llm_provider_configs` | `(provider, is_active)` | Composite |
| `llm_usage_logs` | `(created_at)` | B-tree (for budget aggregation) |
| `llm_usage_logs` | `(evolution_run_id)` | B-tree (FK lookup) |
| `nta_page_snapshots` | `(target_page_id, crawled_at)` | Composite |
| `nta_page_snapshots` | `(content_hash)` | B-tree (change detection) |
| `nta_crawler_runs` | `(started_at)` | B-tree (history listing) |
| `evolution_runs` | `(status)` | B-tree (pending review filter) |
| `evolution_runs` | `(created_at)` | B-tree (history listing) |
| `generation_attempts` | `(evolution_run_id)` | B-tree (FK lookup) |
| `audit_logs` | `(entity_type, entity_id)` | Composite |
| `audit_logs` | `(created_at)` | B-tree (history listing) |
| `notification_logs` | `(event, created_at)` | Composite |
| `notification_logs` | `(evolution_run_id)` | B-tree (FK lookup) |
| `bootstrap_verification_reports` | `(function_name)` | B-tree |

---

## 4. API Surface

### 4.1 Full Endpoint Table

| Phase | Method | Path | Purpose |
|---|---|---|---|
| 1 | GET | `/health` | API + DB health check |
| 3 | POST | `/users` | Create a user |
| 3 | GET | `/users/{user_id}` | Get user by ID |
| 3 | POST | `/income-entries` | Create income entry |
| 3 | GET | `/income-entries/{user_id}` | List income entries for user |
| 3 | GET | `/income-entries/{user_id}/{entry_id}` | Get single income entry |
| 3 | DELETE | `/income-entries/{user_id}/{entry_id}` | Delete income entry |
| 3 | GET | `/tax-profiles/{user_id}/{year}` | Get annual tax profile |
| 3 | PUT | `/tax-profiles/{user_id}/{year}` | Create or update tax profile |
| 3 | GET | `/profile-definition/{year}` | Schema discovery for agents |
| 4 | POST | `/ingestion/upload` | Upload document for MarkItDown processing |
| 5 | POST | `/tax/calculate/{user_id}/{year}` | Run tax calculations |
| 5 | GET | `/algorithms` | List registered algorithms |
| 5 | GET | `/algorithms/{function_name}` | Get algorithm details |
| 5 | POST | `/algorithms` | Register new algorithm |
| 5 | PUT | `/algorithms/{id}/activate` | Activate an algorithm version |
| 6A | PUT | `/admin/llm/config` | Create/update LLM provider config |
| 6A | GET | `/admin/llm/config` | Get active LLM config (masked token) |
| 6A | POST | `/admin/llm/test` | Test LLM connection |
| 6A | GET | `/admin/llm/usage` | Get LLM usage summary |
| 6B | POST | `/admin/nta/check` | Trigger NTA crawl |
| 6B | GET | `/admin/nta/pages` | List target NTA pages |
| 6B | POST | `/admin/nta/pages` | Add target NTA page |
| 6B | PUT | `/admin/nta/pages/{id}` | Update target NTA page |
| 6B | GET | `/admin/nta/snapshots/{id}` | Get snapshot details + markdown |
| 6B | GET | `/admin/nta/health` | Crawler health status |
| 6B | GET | `/admin/nta/runs` | List crawl runs |
| 6-Pre | POST | `/admin/bootstrap/run` | Run bootstrap process |
| 6-Pre | GET | `/admin/bootstrap/report` | Get verification report |
| 6E | POST | `/admin/evolution/run` | Trigger evolution pipeline |
| 6E | GET | `/admin/evolution/runs` | List evolution runs |
| 6E | GET | `/admin/evolution/runs/{id}` | Get evolution run detail |
| 6E | POST | `/admin/evolution/runs/{id}/review` | Submit review decision |
| 6E | POST | `/admin/evolution/runs/{id}/rollback` | Rollback to previous version |
| 6F | PUT | `/admin/notifications/config` | Create/update notification config |
| 6F | GET | `/admin/notifications/config` | Get active notification config |
| 6F | POST | `/admin/notifications/test` | Send test notification |
| 6F | GET | `/admin/notifications/log` | Get notification log |

### 4.2 Response Envelope

All error responses follow this structure for agent consumption:

```json
{
  "error_code": "MISSING_REQUIRED_FIELD",
  "detail": "Missing 'spouse_income' field. Required when 'has_spouse' is true."
}
```

All success responses use typed Pydantic `response_model` with `Field(description=...)` on every field.

---

## 5. Technical Stack

| Component | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Required for modern typing, asyncio improvements |
| Web Framework | FastAPI (Async) | Native OpenAPI generation, async-first, agent-friendly |
| ORM | SQLAlchemy 2.0 (Async) | `Mapped`/`mapped_column` style, async session support |
| Database | PostgreSQL 15+ | JSONB support for adaptive schema, production-grade |
| Validation | Pydantic v2 | `Field(description=...)` for agent-readable schemas |
| Migration | Alembic (Async) | Autogenerate from SQLAlchemy models |
| Ingestion | microsoft/markitdown | PDF/Excel/Image to Markdown conversion |
| Config | pydantic-settings | Type-safe `.env` loading |
| Dashboard | Streamlit | Rapid admin UI for Evolution Loop |
| Containerization | Docker Compose | Local dev: `db` (PostgreSQL) + `api` (FastAPI) |
| Linter/Formatter | Ruff | Fast, single-tool replacement for flake8+black+isort |
| Testing | pytest + httpx | Async test client via `ASGITransport` |

---

## 6. Cross-Cutting Concerns

### 6.1 Configuration

All config loaded via `pydantic-settings` from environment variables / `.env`:

```python
class Settings(BaseSettings):
    database_url: str
    postgres_user: str
    postgres_password: str
    postgres_db: str
    log_level: str = "INFO"
    model_config = SettingsConfigDict(env_file=".env")
```

### 6.2 Logging

Centralized in `backend/src/logging_config.py`. Every module uses:

```python
from src.logging_config import get_logger
logger = get_logger(__name__)
```

Levels: DEBUG (tracing), INFO (business events), WARNING (recoverable), ERROR (failures).

### 6.3 Error Handling

FastAPI exception handlers return structured JSON:

```python
{
    "error_code": "RESOURCE_NOT_FOUND",  # machine-readable slug
    "detail": "TaxProfile for user abc123, year 2024 not found."  # human-readable
}
```

Agents branch on `error_code`, not string matching.

### 6.4 Testing Strategy

> Full policy: `.cursor/rules/testing-policy.md`

#### Philosophy: "Zero Tolerance for Math Errors"

Tax calculation is deterministic. All final JPY amounts use exact integer assertions — never `approx()` or floating-point comparisons.

#### Test Layers

| Layer | Target | Mock DB? | Mock External? | Purpose |
|-------|--------|----------|----------------|---------|
| **Unit** | `domain/tax_calculations.py` | N/A | N/A | Pure function logic, 100% branch coverage |
| **Service** | `application/tax_service.py` | Yes | Yes | Orchestration correctness |
| **Integration** | `api/*_routes.py` | No (test container) | Yes | HTTP + DB round-trip |
| **Adapter** | `infrastructure/*` | Yes | Yes | Data transformation boundaries |

#### Golden Data Protocol

Official government tools serve as the "oracle" for expected values:
- **Income Tax:** NTA Kakutei Shinkoku Corner (https://www.keisan.nta.go.jp/)
- **Furusato Nozei:** MIC Simulation Excel
- **Resident Tax:** Local government simulators

Golden data files live in `backend/tests/golden_data/` as JSON with full traceability (tax year, oracle source, verified date, law references). AI agents must **never** invent expected tax values — only use NTA-verified data.

#### Tax-Specific Test Requirements

1. **Year-versioned regression:** Adding new tax year logic must not break existing year tests.
2. **Boundary tests:** Every bracket threshold tested at ± 1 JPY.
3. **Invariant tests:** Tax >= 0, monotonically increasing, effective rate bounded, taxable income floors to zero.
4. **Cross-deduction scenarios:** Realistic combinations (married + dependents + iDeCo + insurance).

#### Coverage Targets

| Scope | Threshold |
|-------|-----------|
| `domain/` (tax logic) | >= 95% branch coverage |
| Overall backend | >= 80% line coverage |

#### Tooling

- **Async:** `asyncio_mode = "auto"` in `pyproject.toml` — no manual `@pytest.mark.asyncio`.
- **HTTP client:** `httpx.AsyncClient` + `ASGITransport` for API integration tests.
- **Mocking:** `unittest.mock.patch` or `pytest-mock`. **Never** mock `domain/tax_calculations.py`.

---

## 7. Phase Dependency Graph

```
Phase 1 ──► Phase 2 ──► Phase 3 ──┬──► Phase 4
(Scaffold)  (Data)      (CRUD API) │   (Ingestion)
                                   │
                                   └──► Phase 5 ──► Phase 6
                                       (Tax Engine) (Evolution)
```

| Phase | Document | Depends On | Deliverable |
|---|---|---|---|
| 1 | `Phase1_Scaffold.md` | None | Docker + FastAPI + health endpoint |
| 2 | `Phase2_DataModels.md` | Phase 1 | 5 SQLAlchemy models + Alembic migrations |
| 3 | `Phase3_CrudApi.md` | Phase 2 | Full CRUD API + Pydantic schemas |
| 4 | `Phase4_Ingestion.md` | Phase 3 | MarkItDown upload pipeline |
| 5 | `Phase5_TaxEngine.md` | Phase 3 | Tax calculations + algorithm registry |
| 6 | `Phase6_Evolution.md` | Phase 5 | NTA monitor + admin dashboard |

Phases 4 and 5 can be developed in parallel after Phase 3 is complete.
