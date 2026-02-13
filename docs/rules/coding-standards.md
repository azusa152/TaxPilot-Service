# Coding Standards — Clean Code + Clean Architecture

## Working with Existing Code
- Before writing new modules, check existing files in the same layer for patterns to follow.
- Reference actual files as examples (e.g., `backend/src/api/routes.py` for route patterns, `backend/src/infrastructure/models.py` for model patterns).
- When in doubt, match the style of the nearest existing file rather than inventing a new convention.

## Stack
- Python 3.11+
- FastAPI (Async)
- SQLAlchemy (Async 2.0 style — `Mapped` / `mapped_column`)
- Pydantic v2
- PostgreSQL (JSONB for adaptive schema)
- Alembic (Async migrations)
- Streamlit (Dashboard)

## Clean Architecture (Layered Structure)

All backend code lives under `backend/src/` with strict layer separation:

- **`domain/`** — Pure business rules, entities, enums, constants. No framework imports allowed.
- **`application/`** — Use-case orchestration and service functions. Depends only on `domain/` and repository interfaces.
- **`infrastructure/`** — External adapters (PostgreSQL, MarkItDown, external APIs). Implements interfaces defined by upper layers.
- **`api/`** — FastAPI route handlers. Thin controllers that delegate to `application/` services.
- New code must be placed in the correct layer; never leak infrastructure concerns into `domain/`.

### Dependency Rules

```
api/ → application/ → domain/
         ↓
    infrastructure/  → domain/
```

- `domain/` imports nothing from other layers.
- `application/` imports from `domain/` only.
- `infrastructure/` imports from `domain/` and `config`.
- `api/` imports from `domain/`, `application/`, and `infrastructure/`.

## Clean Code Practices
- **Small, focused functions:** Each function should do one thing well with a descriptive name.
- **No magic numbers or strings:** Use `domain/constants.py` for all thresholds, tax rates, and configuration values.
- **DRY (Don't Repeat Yourself):** Extract duplicated logic into shared helpers or modules.
- **Pure functions:** Prefer pure functions and immutable data where possible; isolate side effects at the boundary.

## Style Guide
1. **Type Hinting:** Mandatory everywhere. Use `typing.Optional`, `typing.List`, `dict[str, Any]`, etc.
2. **Docstrings:** Google Style. Required for all public functions and API endpoints.
3. **Async/Await:** Use `async def` for all I/O bound operations (DB, Network).
4. **Dependency Injection:** Use `Depends()` for DB sessions and services.
5. **Pydantic v2:** Use `Field(description="...")` on all schema fields — agents read these descriptions to understand parameters.
6. **Response models:** Use `model_config = {"from_attributes": True}` for ORM-backed responses.

## Python Tooling
- **Formatter/Linter:** Use `ruff` for both formatting and linting. Run `make lint` and `make format` before committing.
- **Import ordering:** stdlib, third-party, local — ruff handles this automatically.
- **Makefile shortcuts:** Use `make test`, `make lint`, `make format` from the project root. Run `make help` to see all targets.
- **Dependencies:** Pin minimum versions in `backend/pyproject.toml`.

## Logging
- Use `from src.logging_config import get_logger` and `logger = get_logger(__name__)` in every backend module.
- Never use `print()` for diagnostic output; always use `logger.info()` / `logger.warning()` / `logger.error()`.
- Log levels: DEBUG for tracing, INFO for business events, WARNING for recoverable issues, ERROR for failures.

## Security
- Never hardcode secrets, API keys, or tokens in source code.
- Use `pydantic-settings` with `.env` for all configuration. Reference `.env.example` for required variables.
- Never commit `.env` files. Only commit `.env.example` with placeholder values.

---

# Backend Testing Standards (pytest)

Every feature MUST ship with tests. No untested code in production.

## Test File Structure

Tests live in `backend/tests/` mirroring the source layout:

```
backend/tests/
├── conftest.py
├── api/
│   └── test_health.py
├── application/
│   └── test_<service>.py
├── infrastructure/
│   └── test_ingestion.py
└── domain/
    └── test_<logic>.py
```

## Test Naming

Use descriptive names: `test_<function>_should_<expected_behavior>`

```python
# GOOD
def test_create_income_entry_should_return_201_on_valid_input(): ...
def test_health_should_return_healthy_status(): ...

# BAD
def test_income(): ...
def test_1(): ...
```

## AAA Pattern

Every test follows **Arrange / Act / Assert**:

```python
def test_health_should_return_healthy_status(client):
    # Arrange — test client from fixture

    # Act
    response = await client.get("/health")

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
```

## Fixtures & conftest.py

- `conftest.py` provides: `AsyncClient` via `httpx.ASGITransport`, mock DB sessions where needed.
- Use `@pytest.fixture` with appropriate scope (`session` for DB, `function` for per-test isolation).
- `asyncio_mode = "auto"` is configured in `pyproject.toml` — no need for `@pytest.mark.asyncio` decorators.

## Mock External Services

- **MarkItDown**, **external APIs**, and any network I/O MUST be mocked in unit tests. Never hit real services.
- Use `unittest.mock.patch` or `pytest-mock` to replace infrastructure adapters.

## Minimum Test Coverage Per Endpoint

| Scenario | Status Code |
|----------|-------------|
| Happy path | 200 / 201 |
| Validation error | 422 |
| Not found | 404 |
| Conflict / duplicate | 409 (where applicable) |

## Golden Rule

All tax calculation logic must have unit tests covering edge cases. This is non-negotiable — deterministic calculations are the core value of TaxPilot.
