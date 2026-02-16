---
description: Testing standards and quality assurance for TaxPilot. Apply when writing or modifying tests, implementing tax logic, or reviewing test coverage.
globs:
  - "backend/tests/**"
  - "backend/src/domain/tax_calculations.py"
  - "backend/src/application/tax_service.py"
  - "**/*test*.py"
  - "**/conftest.py"
alwaysApply: false
---

# Testing Standards & Quality Assurance

**Scope:** TaxPilot Service (Backend + Frontend)
**Audience:** Human Developers & AI Agents (Cursor, Claude)

Every feature MUST ship with tests. No untested code in production.

---

## 1. Core Philosophy: "Zero Tolerance for Math Errors"

This system calculates taxes. Tax calculation is **deterministic** — not probabilistic.

- **Precision:** Japanese Yen (JPY) are integers. **NEVER** use `approx()` or floating-point assertions for final tax amounts. All assertions must use **exact integer equality**.
- **Reproducibility:** Given the same inputs and tax year, the output must be identical across runs, environments, and time.
- **Auditability:** Every calculation result must be traceable back to a specific NTA regulation and verifiable against official government tools.

---

## 2. Test Structure & Pyramid

Tests live in `backend/tests/` mirroring the source layout:

```text
backend/tests/
├── conftest.py                  # Global fixtures (Async DB session, HTTP client)
├── domain/                      # Unit Tests: Pure logic, zero I/O
│   ├── test_tax_calculations.py
│   └── ...
├── application/                 # Service Tests: Orchestration logic
│   └── test_tax_service.py
├── api/                         # Integration Tests: HTTP + DB flow
│   ├── test_health.py
│   ├── test_tax.py
│   ├── test_income_entries.py
│   └── ...
├── infrastructure/              # Adapter Tests: DB models, parsers
│   ├── test_models.py
│   ├── test_markitdown_adapter.py
│   └── ...
└── golden_data/                 # The "Ground Truth" — NTA-verified cases
    ├── nta_case_2024_salary_basic.json
    ├── nta_case_2024_spouse_dependents.json
    └── ...
```

### 2.1 Unit Tests — The Logic Core (HIGHEST PRIORITY)

- **Target:** `backend/src/domain/tax_calculations.py`
- **Requirement:** No database access. No API calls. No mocks needed. Pure Python function testing.
- **Coverage:** 100% branch coverage required for all tax calculation functions.
- **Year-Versioning:** Every test must specify which tax year's rules it validates.

```python
def test_calc_basic_deduction_2024_standard_income():
    """
    Verifies basic deduction for standard income under 2024 rules.

    Tax Year: 2024
    Source: NTA No.1199 (基礎控除)
    Ground Truth: Verified via NTA Simulation Tool 2024
    """
    assert calc_basic_deduction(5_000_000) == 480_000
```

### 2.2 Service Tests — Orchestration Logic

- **Target:** `backend/src/application/tax_service.py`, other services
- **Requirement:** Mock infrastructure (DB queries), test that services correctly orchestrate domain functions.
- **Focus:** Verify that `tax_service.calculate()` correctly aggregates income entries, applies deductions in the right order, and returns a complete `TaxCalculationResult`.

### 2.3 Integration Tests — The Data Flow

- **Target:** `backend/src/api/` routes and `backend/src/infrastructure/models.py`
- **Requirement:**
  - Use `pytest-asyncio` with `asyncio_mode = "auto"` (no manual decorators needed).
  - Use the test PostgreSQL container (via `conftest.py` fixtures).
  - Verify that JSONB `additional_attributes` fields correctly store and retrieve dynamic attributes.
  - Cover all HTTP status codes: 200/201 (happy), 404 (not found), 422 (validation), 409 (conflict).

### 2.4 Adapter Tests — Infrastructure Boundaries

- **Target:** `backend/src/infrastructure/` (MarkItDown, Algorithm Loader, etc.)
- **Requirement:** Mock external I/O (file system, network). Verify adapters correctly transform data between external formats and domain types.

---

## 3. The "Golden Data" Protocol (Ground Truth)

Since AI models cannot "know" if a calculation is legally correct, we rely on **Official Government Tools** as the Oracle.

### 3.1 Approved Oracles

| Tax Type | Oracle | URL |
|----------|--------|-----|
| Income Tax | NTA Kakutei Shinkoku Corner | https://www.keisan.nta.go.jp/ |
| Furusato Nozei | MIC Simulation Excel | https://www.soumu.go.jp/main_sosiki/jichi_zeisei/czaisei/czaisei_seido/furusato/mechanism/deduction.html |
| Resident Tax | Official local government simulators | (e.g., Shinjuku City, Shibuya City) |

### 3.2 Golden Data File Format

Each golden data file is a JSON document with full traceability:

```json
{
  "case_id": "nta_2024_salary_basic_01",
  "tax_year": 2024,
  "description": "Standard salaried employee, single, no dependents",
  "source": {
    "oracle": "NTA Kakutei Shinkoku Corner",
    "url": "https://www.keisan.nta.go.jp/",
    "verified_date": "2025-01-15",
    "verified_by": "human"
  },
  "input": {
    "gross_salary": 5000000,
    "social_insurance_premium": 600000,
    "has_spouse": false,
    "spouse_income": 0,
    "dependents_count": 0,
    "life_insurance_premium": 0,
    "ideco_monthly_contribution": 0
  },
  "expected_output": {
    "salary_income_deduction": 1440000,
    "basic_deduction": 480000,
    "social_insurance_deduction": 600000,
    "taxable_income": 2480000,
    "income_tax": 150500,
    "furusato_limit": 49000
  },
  "law_references": [
    "NTA No.1410 (Salary Income Deduction / 給与所得控除)",
    "NTA No.1199 (Basic Deduction / 基礎控除)",
    "NTA No.2260 (Income Tax Rate Table / 所得税の税率)"
  ]
}
```

### 3.3 Implementation Rule for AI Agents

When asked to write a test for a tax calculation function, you **MUST**:

1. **Ask** the user for a "Golden Case" (input/output pair verified by the NTA tool) if none exists.
2. **Create** a test case that inputs those exact parameters.
3. **Assert** the result matches the NTA output **exactly** (integer equality).
4. **Document** the oracle source in the test docstring.
5. **Store** the golden data in `backend/tests/golden_data/` for regression use.

**NEVER** invent expected values for tax calculations. If you cannot verify the expected output against an official oracle, mark the test as `@pytest.mark.skip(reason="Awaiting NTA verification")`.

---

## 4. Tax-Specific Testing Requirements

### 4.1 Year-Versioned Regression

Tax rules change annually. Tests must guarantee backward compatibility:

```python
# 2024 rules — must continue passing even when 2025 logic is added
def test_calc_income_tax_2024_second_bracket():
    """2024 progressive bracket: 3M taxable -> 202,500 JPY."""
    assert calc_income_tax(3_000_000) == 202_500

# 2025 rules — separate test functions
def test_calc_income_tax_2025_second_bracket():
    """2025 progressive bracket (if rates changed)."""
    assert calc_income_tax_2025(3_000_000) == ...  # NTA-verified value
```

**Rule:** Adding a new tax year MUST NOT break existing year tests. This is enforced by running the full test suite on every commit.

### 4.2 Mandatory Boundary Tests

Every tax calculation function MUST have tests at these boundaries:

| Boundary | Examples |
|----------|---------|
| **Zero input** | Income = 0, premium = 0, dependents = 0 |
| **Just below threshold** | 1,949,999 JPY (below bracket change at 1,950,000) |
| **Exactly at threshold** | 1,950,000 JPY |
| **Just above threshold** | 1,950,001 JPY |
| **Maximum/cap values** | Salary deduction cap at 1,950,000; basic deduction phase-out above 24M |
| **Floor to zero** | Deductions exceeding income should floor taxable income to 0 |

```python
def test_taxable_income_should_floor_to_zero():
    """Taxable income must never go negative even when deductions exceed income."""
    result = calc_taxable_income(
        gross_salary=500_000,
        social_insurance_premium=0,
        life_insurance_premium=0,
        has_spouse=True,
        spouse_income=0,
        dependents_count=5,
        ideco_monthly=23_000,
    )
    assert result == 0
```

### 4.3 Invariant / Property Tests

Tax calculations have mathematical invariants that must always hold:

```python
import pytest

SAMPLE_INCOMES = [0, 500_000, 1_950_000, 3_000_000, 5_000_000, 10_000_000, 20_000_000]

@pytest.mark.parametrize("income", SAMPLE_INCOMES)
def test_income_tax_is_non_negative(income):
    """Income tax must never be negative."""
    assert calc_income_tax(income) >= 0

@pytest.mark.parametrize("income", SAMPLE_INCOMES)
def test_income_tax_is_monotonically_increasing(income):
    """Higher taxable income should never produce lower tax."""
    if income > 0:
        assert calc_income_tax(income) >= calc_income_tax(income - 1)

@pytest.mark.parametrize("income", SAMPLE_INCOMES)
def test_salary_deduction_does_not_exceed_income(income):
    """Salary income deduction should never exceed gross salary."""
    assert calc_salary_income_deduction(income) <= income

@pytest.mark.parametrize("income", SAMPLE_INCOMES)
def test_effective_tax_rate_below_maximum_bracket(income):
    """Effective tax rate should never exceed the top marginal rate (45%)."""
    tax = calc_income_tax(income)
    if income > 0:
        assert tax / income <= 0.45
```

### 4.4 Cross-Deduction Interaction Tests

Individual deduction tests are not sufficient. Test realistic full-scenario combinations:

```python
def test_full_scenario_married_with_dependents_and_ideco():
    """
    Realistic scenario: Married salaried worker, 2 dependents, iDeCo contributor.

    Tax Year: 2024
    Ground Truth: Verified via NTA Simulation Tool 2024
    """
    gross = 8_000_000
    social = 900_000
    life = 50_000
    ideco = 23_000  # monthly

    taxable = calc_taxable_income(
        gross_salary=gross,
        social_insurance_premium=social,
        life_insurance_premium=life,
        has_spouse=True,
        spouse_income=500_000,
        dependents_count=2,
        ideco_monthly=ideco,
    )
    tax = calc_income_tax(taxable)

    # Verified against NTA tool — exact integer match
    assert taxable == ...  # Fill with NTA-verified value
    assert tax == ...      # Fill with NTA-verified value
```

### 4.5 Adaptive Schema (JSONB) Testing

Since TaxPilot uses `additional_attributes` JSONB for year-specific fields:

```python
async def test_tax_profile_stores_and_retrieves_dynamic_fields(client):
    """JSONB additional_attributes round-trips correctly."""
    profile_data = {
        "has_spouse": True,
        "dependents_count": 1,
        "additional_attributes": {
            "fixed_tax_cut_eligible": True,
            "fixed_tax_cut_dependents": 2
        }
    }
    response = await client.put("/tax-profiles/user1/2024", json=profile_data)
    assert response.status_code == 200

    get_response = await client.get("/tax-profiles/user1/2024")
    data = get_response.json()
    assert data["additional_attributes"]["fixed_tax_cut_eligible"] is True
    assert data["additional_attributes"]["fixed_tax_cut_dependents"] == 2
```

### 4.6 Algorithm Registry Safety Tests

Hot-loaded algorithms from the Evolution Loop must be tested before activation:

```python
def test_algorithm_registry_rejects_syntax_error():
    """Algorithm with syntax error must not be activated."""
    ...

def test_algorithm_registry_rejects_import_violations():
    """Algorithm code must not import dangerous modules (os, subprocess, etc.)."""
    ...

def test_algorithm_output_matches_golden_data():
    """New algorithm version must produce identical results to golden data."""
    ...
```

---

## 5. Coding Standards for Tests

### 5.1 Naming Conventions

- **Files:** `test_<module_name>.py`
- **Functions:** `test_<function_name>_<scenario>` or `test_<function_name>_should_<expected_behavior>`

```python
# GOOD — descriptive, specific
def test_calc_income_tax_zero_input(): ...
def test_calc_income_tax_first_bracket_boundary(): ...
def test_calc_spouse_deduction_should_return_zero_when_taxpayer_over_limit(): ...
def test_create_income_entry_should_return_201_on_valid_input(): ...

# BAD — vague, untraceable
def test_calc(): ...
def test_tax_1(): ...
def test_income(): ...
```

### 5.2 Docstrings (Traceability)

Every test case involving tax logic **MUST** include:

```python
def test_calc_basic_deduction_2024_standard():
    """
    Verifies basic deduction logic for standard income.

    Tax Year: 2024
    Source: NTA No.1199 (Basic Deduction / 基礎控除)
    Ground Truth: Verified via NTA Simulation Tool v2024
    """
    assert calc_basic_deduction(5_000_000) == 480_000
```

Required docstring fields for tax tests:
- **Tax Year** — which year's rules are being tested
- **Source** — the NTA regulation number or law reference
- **Ground Truth** — the oracle used for verification

### 5.3 AAA Pattern

Every test follows **Arrange / Act / Assert** with clear section comments:

```python
async def test_health_should_return_healthy_status(client):
    # Arrange — test client from fixture

    # Act
    response = await client.get("/health")

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
```

### 5.4 Async Testing

Since we use FastAPI and Async SQLAlchemy:
- `asyncio_mode = "auto"` is configured in `pyproject.toml` — **no need** for `@pytest.mark.asyncio` decorators.
- Use `async def` and the `db_session` / `client` fixtures from `conftest.py`.

### 5.5 Fixtures & conftest.py

- `conftest.py` provides: `AsyncClient` via `httpx.ASGITransport`, test DB sessions.
- Use `@pytest.fixture` with appropriate scope (`session` for DB, `function` for per-test isolation).

### 5.6 Mocking Rules

| What | Mock? | Why |
|------|-------|-----|
| Tax calculation functions (`domain/`) | **NEVER** | These are the core value — always test real logic |
| Database queries | **Yes** (in unit/service tests) | Isolate business logic from I/O |
| MarkItDown adapter | **Yes** | External library, non-deterministic |
| External APIs (NTA crawler, LLM) | **Yes** | Network I/O, non-deterministic |
| File system I/O | **Yes** | Environment-dependent |

Use `unittest.mock.patch` or `pytest-mock` to replace infrastructure adapters.

---

## 6. Test Scenarios by Module

### Income Entries
| Scenario | What to test |
|----------|-------------|
| Create income entry | Valid payload returns 201 with correct fields |
| Validation error | Missing required fields (e.g., `gross_amount`) returns 422 |
| Invalid income type | Non-enum value for `income_type` returns 422 |
| List by user | Returns all entries for a given user_id |

### Tax Profiles
| Scenario | What to test |
|----------|-------------|
| Get profile | Returns core fields + JSONB `additional_attributes` |
| Update profile | PUT merges JSONB fields correctly |
| Profile not found | Non-existent user/year returns 404 |
| Dynamic fields | JSONB `additional_attributes` round-trips correctly |

### Profile Definition (Schema Discovery)
| Scenario | What to test |
|----------|-------------|
| Get definition | Returns `schema_definition` JSONB for the requested year |
| Year not found | Non-existent year returns 404 |

### Document Ingestion
| Scenario | What to test |
|----------|-------------|
| Upload PDF | MarkItDown processes file and returns Markdown content |
| Unsupported format | Graceful error with meaningful message |
| MarkItDown failure | Adapter failure is caught and returns 500 with `error_code` |

### Tax Calculations
| Scenario | What to test |
|----------|-------------|
| Individual deductions | Each deduction function at zero, mid, cap, and boundary values |
| Bracket boundaries | Income at threshold ± 1 JPY |
| Full scenarios | Realistic combinations (married, dependents, iDeCo, etc.) |
| Invariants | Non-negative tax, monotonic increase, effective rate bounded |
| Year regression | Prior-year tests must not break when new year logic is added |
| Golden data | NTA-verified input/output pairs as ground truth |

### Minimum HTTP Status Coverage Per Endpoint

| Scenario | Status Code |
|----------|-------------|
| Happy path | 200 / 201 |
| Validation error | 422 |
| Not found | 404 |
| Conflict / duplicate | 409 (where applicable) |

---

## 7. Frontend Testing Standards

### 7.1 Component Tests

- Use **Vitest** + **React Testing Library** for component tests.
- Test that tax result displays show correct formatted values (e.g., "¥150,500").
- Test that locale switching (en/ja/zh-TW) renders correct translations.

### 7.2 Visual Regression (Optional)

- Use **Playwright** for end-to-end smoke tests of the calculate page.
- Verify the tax breakdown chart renders without errors.

---

## 8. Coverage & CI Enforcement

### 8.1 Coverage Thresholds

| Scope | Target | Tool |
|-------|--------|------|
| `domain/` (tax logic) | >= 95% branch | `pytest --cov=src/domain --cov-branch` |
| Overall backend | >= 80% line | `pytest --cov=src` |

### 8.2 Required Checks Before Merge

| Check | Threshold | Tool |
|-------|-----------|------|
| All unit tests pass | 100% pass rate | `pytest backend/tests/domain/` |
| All integration tests pass | 100% pass rate | `pytest backend/tests/api/` |
| Domain coverage | >= 95% branch coverage | `pytest --cov=src/domain --cov-branch` |
| Overall coverage | >= 80% line coverage | `pytest --cov=src` |
| Linting | Zero errors | `ruff check` |
| Golden data tests | 100% pass rate | `pytest -m golden` |

### 8.3 Regression Gate

When adding or modifying tax calculation logic:
1. All existing golden data tests must still pass.
2. New logic must include at least one new golden data case.
3. PR description must reference the NTA regulation being implemented or changed.

---

## 9. Instructions for Cursor / AI Agents

When generating or modifying code:

1. **TDD First:** Before implementing a complex calculation function, write the test case first using the "Golden Data" provided by the user.

2. **Edge Cases:** Always generate tests for boundary conditions:
   - Income = 0
   - Income just below a tax bracket threshold (e.g., 1,949,999 JPY)
   - Income exactly at a tax bracket threshold (e.g., 1,950,000 JPY)
   - Income just above a tax bracket threshold (e.g., 1,950,001 JPY)
   - Deductions exceeding income (floor to zero)

3. **Mocking:**
   - Mock external calls (OpenAI API, MarkItDown, NTA Crawler).
   - **NEVER** mock the tax calculation logic itself.

4. **Golden Data:**
   - **NEVER** invent expected tax values. If no golden data exists, ask the user.
   - If you must write a placeholder test, use `pytest.mark.skip(reason="Awaiting NTA verification")`.

5. **Invariants:**
   - When adding a new calculation function, add invariant tests (non-negative, monotonic, bounded).

6. **Year Awareness:**
   - Always check `DEFAULT_TAX_YEAR` in `domain/constants.py`.
   - New tax year logic goes in new functions (e.g., `calc_income_tax_2025`), not by modifying existing year functions.
   - Existing year tests must never be modified or deleted.
