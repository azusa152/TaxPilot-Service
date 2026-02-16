# Phase 5: Tax Calculation Engine
**Goal:** Implement core Japanese tax calculation algorithms as pure domain functions, build the Algorithm Registry operations, and expose calculation endpoints.

**Depends on:** Phase 3 (CRUD API for TaxProfile and IncomeEntry must be working)
**Produces:** Deterministic tax calculation functions, calculation endpoint, algorithm registry CRUD and activation

---

## Context

This is the **core value** of TaxPilot. Tax calculations must be:
1. **Deterministic** — pure Python functions, no LLM math, no randomness.
2. **Testable** — every function is a pure function in `domain/` with zero framework dependencies.
3. **Traceable** — linked to NTA regulations via `AlgorithmRegistry.source_law_hash`.
4. **Versioned** — multiple versions can coexist; only `ACTIVE` versions are executed.

**Key calculations for the MVP (2024 tax year):**
- Salary income deduction (給与所得控除)
- Basic deduction (基礎控除)
- Social insurance deduction (社会保険料控除)
- Life insurance deduction (生命保険料控除)
- Spouse deduction (配偶者控除)
- Dependents deduction (扶養控除)
- iDeCo deduction (小規模企業共済等掛金控除)
- Furusato Nouzei optimal limit (ふるさと納税上限)
- Income tax calculation (所得税)

---

## Tasks

### Task 5.1: Tax Calculation Functions (Domain Layer)

**File:** `backend/src/domain/tax_calculations.py`

All functions are **pure** — they take numbers in, return numbers out. No DB, no async, no framework imports.

```python
"""Deterministic Japanese tax calculation functions.

All amounts are in JPY (integers). All functions are pure — no side effects.
Reference: National Tax Agency (NTA) Japan, 2024 tax year.
"""


def calc_salary_income_deduction(gross_salary: int) -> int:
    """Calculate salary income deduction (給与所得控除).

    Based on NTA 2024 table:
    - Up to 1,625,000: 550,000
    - Up to 1,800,000: gross * 40% - 100,000
    - Up to 3,600,000: gross * 30% + 80,000
    - Up to 6,600,000: gross * 20% + 440,000
    - Up to 8,500,000: gross * 10% + 1,100,000
    - Over 8,500,000: 1,950,000 (cap)
    """
    if gross_salary <= 0:
        return 0
    if gross_salary <= 1_625_000:
        return 550_000
    if gross_salary <= 1_800_000:
        return int(gross_salary * 0.4) - 100_000
    if gross_salary <= 3_600_000:
        return int(gross_salary * 0.3) + 80_000
    if gross_salary <= 6_600_000:
        return int(gross_salary * 0.2) + 440_000
    if gross_salary <= 8_500_000:
        return int(gross_salary * 0.1) + 1_100_000
    return 1_950_000


def calc_basic_deduction(total_income: int) -> int:
    """Calculate basic deduction (基礎控除).

    2024: 480,000 for income <= 24,000,000; phased out above.
    """
    if total_income <= 24_000_000:
        return 480_000
    if total_income <= 24_500_000:
        return 320_000
    if total_income <= 25_000_000:
        return 160_000
    return 0


def calc_spouse_deduction(has_spouse: bool, taxpayer_income: int, spouse_income: int = 0) -> int:
    """Calculate spouse deduction (配偶者控除).

    Simplified 2024 rules:
    - Taxpayer income must be <= 10,000,000
    - Spouse income must be <= 480,000 (after salary deduction)
    - Base deduction: 380,000
    """
    if not has_spouse:
        return 0
    if taxpayer_income > 10_000_000:
        return 0
    if spouse_income > 480_000:
        return 0
    if taxpayer_income <= 9_000_000:
        return 380_000
    if taxpayer_income <= 9_500_000:
        return 260_000
    return 130_000


def calc_dependents_deduction(dependents_count: int) -> int:
    """Calculate dependents deduction (扶養控除).

    Simplified: 380,000 per general dependent.
    Special categories (elderly, specific) are handled via additional_attributes in future.
    """
    if dependents_count <= 0:
        return 0
    return 380_000 * dependents_count


def calc_social_insurance_deduction(premium: int) -> int:
    """Calculate social insurance deduction (社会保険料控除).

    Full amount is deductible.
    """
    return max(0, premium)


def calc_life_insurance_deduction(premium: int) -> int:
    """Calculate life insurance deduction (生命保険料控除).

    Simplified 2024 new contract rules:
    - Up to 20,000: full amount
    - Up to 40,000: premium / 2 + 10,000
    - Up to 80,000: premium / 4 + 20,000
    - Over 80,000: 40,000 (cap)
    """
    if premium <= 0:
        return 0
    if premium <= 20_000:
        return premium
    if premium <= 40_000:
        return premium // 2 + 10_000
    if premium <= 80_000:
        return premium // 4 + 20_000
    return 40_000


def calc_ideco_deduction(monthly_contribution: int) -> int:
    """Calculate iDeCo deduction (小規模企業共済等掛金控除).

    Full annual amount is deductible.
    """
    return max(0, monthly_contribution * 12)


def calc_taxable_income(
    gross_salary: int,
    social_insurance_premium: int,
    life_insurance_premium: int,
    has_spouse: bool,
    dependents_count: int,
    ideco_monthly: int,
    spouse_income: int = 0,
) -> int:
    """Calculate taxable income after all deductions.

    Returns the taxable income (課税所得) in JPY. Minimum 0.
    """
    salary_deduction = calc_salary_income_deduction(gross_salary)
    total_income = gross_salary - salary_deduction

    basic = calc_basic_deduction(total_income)
    social = calc_social_insurance_deduction(social_insurance_premium)
    life_ins = calc_life_insurance_deduction(life_insurance_premium)
    spouse = calc_spouse_deduction(has_spouse, total_income, spouse_income)
    dependents = calc_dependents_deduction(dependents_count)
    ideco = calc_ideco_deduction(ideco_monthly)

    total_deductions = basic + social + life_ins + spouse + dependents + ideco
    taxable = total_income - total_deductions

    return max(0, taxable)


def calc_income_tax(taxable_income: int) -> int:
    """Calculate income tax from taxable income (所得税).

    2024 progressive tax brackets:
    - Up to 1,950,000: 5%
    - Up to 3,300,000: 10% - 97,500
    - Up to 6,950,000: 20% - 427,500
    - Up to 9,000,000: 23% - 636,000
    - Up to 18,000,000: 33% - 1,536,000
    - Up to 40,000,000: 40% - 2,796,000
    - Over 40,000,000: 45% - 4,796,000

    Returns income tax amount (before reconstruction surtax).
    """
    if taxable_income <= 0:
        return 0
    if taxable_income <= 1_950_000:
        return int(taxable_income * 0.05)
    if taxable_income <= 3_300_000:
        return int(taxable_income * 0.10) - 97_500
    if taxable_income <= 6_950_000:
        return int(taxable_income * 0.20) - 427_500
    if taxable_income <= 9_000_000:
        return int(taxable_income * 0.23) - 636_000
    if taxable_income <= 18_000_000:
        return int(taxable_income * 0.33) - 1_536_000
    if taxable_income <= 40_000_000:
        return int(taxable_income * 0.40) - 2_796_000
    return int(taxable_income * 0.45) - 4_796_000


def calc_furusato_limit(
    gross_salary: int,
    social_insurance_premium: int,
    has_spouse: bool,
    dependents_count: int,
    ideco_monthly: int,
) -> int:
    """Calculate optimal Furusato Nouzei donation limit (ふるさと納税上限).

    Simplified formula:
    limit = (income_tax + resident_tax * 20%) / (100% - income_tax_rate * 1.021 - 10%) + 2000

    This is an approximation. The exact calculation depends on marginal tax rate.
    """
    taxable = calc_taxable_income(
        gross_salary, social_insurance_premium, 0, has_spouse, dependents_count, ideco_monthly
    )
    income_tax = calc_income_tax(taxable)

    # Approximate resident tax (10% of taxable income)
    resident_tax = int(taxable * 0.10)

    # Determine marginal income tax rate
    if taxable <= 1_950_000:
        rate = 0.05
    elif taxable <= 3_300_000:
        rate = 0.10
    elif taxable <= 6_950_000:
        rate = 0.20
    elif taxable <= 9_000_000:
        rate = 0.23
    elif taxable <= 18_000_000:
        rate = 0.33
    elif taxable <= 40_000_000:
        rate = 0.40
    else:
        rate = 0.45

    # Furusato limit formula
    denominator = 1.0 - rate * 1.021 - 0.10
    if denominator <= 0:
        return 2_000

    limit = int(resident_tax * 0.20 / denominator) + 2_000
    return max(2_000, limit)
```

### Task 5.2: Tax Calculation Result Schema

**Add to `backend/src/domain/schemas.py`:**

```python
class TaxCalculationResult(BaseModel):
    user_id: str = Field(description="UUID of the user")
    year: int = Field(description="Tax year")
    gross_salary: int = Field(description="Total gross salary for the year in JPY")
    salary_income_deduction: int = Field(description="Salary income deduction amount")
    total_income: int = Field(description="Income after salary deduction")
    basic_deduction: int = Field(description="Basic deduction amount")
    social_insurance_deduction: int = Field(description="Social insurance deduction amount")
    life_insurance_deduction: int = Field(description="Life insurance deduction amount")
    spouse_deduction: int = Field(description="Spouse deduction amount")
    dependents_deduction: int = Field(description="Dependents deduction amount")
    ideco_deduction: int = Field(description="iDeCo deduction amount")
    total_deductions: int = Field(description="Sum of all deductions")
    taxable_income: int = Field(description="Taxable income after all deductions")
    income_tax: int = Field(description="Calculated income tax amount")
    furusato_limit: int = Field(description="Optimal Furusato Nouzei donation limit")
```

### Task 5.3: Tax Service (Application Layer)

**File:** `backend/src/application/tax_service.py`

Orchestrates: fetch profile + sum income entries -> run calculations -> return result.

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.error_handlers import TaxPilotError
from src.application.user_service import get_user
from src.domain.schemas import TaxCalculationResult
from src.domain.tax_calculations import (
    calc_basic_deduction,
    calc_dependents_deduction,
    calc_furusato_limit,
    calc_ideco_deduction,
    calc_income_tax,
    calc_life_insurance_deduction,
    calc_salary_income_deduction,
    calc_social_insurance_deduction,
    calc_spouse_deduction,
    calc_taxable_income,
)
from src.infrastructure.models import IncomeEntry, TaxProfile
from src.logging_config import get_logger

logger = get_logger(__name__)


async def calculate_tax(db: AsyncSession, user_id: str, year: int) -> TaxCalculationResult:
    """Run full tax calculation for a user and year."""
    await get_user(db, user_id)

    # Fetch tax profile
    result = await db.execute(
        select(TaxProfile).where(TaxProfile.user_id == user_id, TaxProfile.year == year)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise TaxPilotError(
            404, "TAX_PROFILE_NOT_FOUND",
            f"Tax profile for user '{user_id}', year {year} not found. Create one first via PUT /tax-profiles/{{user_id}}/{{year}}."
        )

    # Sum annual gross salary from income entries
    entries_result = await db.execute(
        select(IncomeEntry).where(IncomeEntry.user_id == user_id)
    )
    entries = entries_result.scalars().all()
    gross_salary = sum(e.gross_amount for e in entries)

    # Run deterministic calculations
    salary_ded = calc_salary_income_deduction(gross_salary)
    total_income = gross_salary - salary_ded
    basic_ded = calc_basic_deduction(total_income)
    social_ded = calc_social_insurance_deduction(profile.social_insurance_premium)
    life_ded = calc_life_insurance_deduction(profile.life_insurance_premium)
    spouse_ded = calc_spouse_deduction(profile.has_spouse, total_income)
    dep_ded = calc_dependents_deduction(profile.dependents_count)
    ideco_ded = calc_ideco_deduction(profile.ideco_monthly_contribution)

    total_deductions = basic_ded + social_ded + life_ded + spouse_ded + dep_ded + ideco_ded
    taxable = max(0, total_income - total_deductions)
    income_tax = calc_income_tax(taxable)

    furusato = calc_furusato_limit(
        gross_salary, profile.social_insurance_premium,
        profile.has_spouse, profile.dependents_count,
        profile.ideco_monthly_contribution,
    )

    logger.info(f"Tax calculation complete for user {user_id}, year {year}: tax={income_tax}, furusato_limit={furusato}")

    return TaxCalculationResult(
        user_id=user_id,
        year=year,
        gross_salary=gross_salary,
        salary_income_deduction=salary_ded,
        total_income=total_income,
        basic_deduction=basic_ded,
        social_insurance_deduction=social_ded,
        life_insurance_deduction=life_ded,
        spouse_deduction=spouse_ded,
        dependents_deduction=dep_ded,
        ideco_deduction=ideco_ded,
        total_deductions=total_deductions,
        taxable_income=taxable,
        income_tax=income_tax,
        furusato_limit=furusato,
    )
```

### Task 5.4: Algorithm Service (Application Layer)

**File:** `backend/src/application/algorithm_service.py`

CRUD + activation for the AlgorithmRegistry.

```python
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.error_handlers import TaxPilotError
from src.domain.enums import AlgorithmStatus
from src.infrastructure.models import AlgorithmRegistry
from src.logging_config import get_logger

logger = get_logger(__name__)


async def list_algorithms(db: AsyncSession) -> list[AlgorithmRegistry]:
    result = await db.execute(select(AlgorithmRegistry).order_by(AlgorithmRegistry.function_name))
    return list(result.scalars().all())


async def get_algorithm(db: AsyncSession, function_name: str) -> AlgorithmRegistry:
    result = await db.execute(
        select(AlgorithmRegistry)
        .where(AlgorithmRegistry.function_name == function_name, AlgorithmRegistry.status == "ACTIVE")
    )
    algo = result.scalar_one_or_none()
    if algo is None:
        raise TaxPilotError(404, "ALGORITHM_NOT_FOUND", f"No active algorithm with function_name '{function_name}'.")
    return algo


async def register_algorithm(
    db: AsyncSession,
    function_name: str,
    version: str,
    code_content: str,
    source_law_hash: str | None = None,
) -> AlgorithmRegistry:
    algo = AlgorithmRegistry(
        function_name=function_name,
        version=version,
        code_content=code_content,
        status=AlgorithmStatus.DRAFT.value,
        source_law_hash=source_law_hash,
    )
    db.add(algo)
    await db.flush()
    logger.info(f"Registered algorithm '{function_name}' v{version} as DRAFT")
    return algo


async def activate_algorithm(db: AsyncSession, algorithm_id: int) -> AlgorithmRegistry:
    result = await db.execute(select(AlgorithmRegistry).where(AlgorithmRegistry.id == algorithm_id))
    algo = result.scalar_one_or_none()
    if algo is None:
        raise TaxPilotError(404, "ALGORITHM_NOT_FOUND", f"Algorithm with id {algorithm_id} not found.")

    # Archive previous active version of the same function
    await db.execute(
        update(AlgorithmRegistry)
        .where(
            AlgorithmRegistry.function_name == algo.function_name,
            AlgorithmRegistry.status == AlgorithmStatus.ACTIVE.value,
        )
        .values(status=AlgorithmStatus.ARCHIVED.value)
    )

    algo.status = AlgorithmStatus.ACTIVE.value
    await db.flush()
    logger.info(f"Activated algorithm '{algo.function_name}' v{algo.version} (id={algo.id})")
    return algo
```

### Task 5.5: Tax & Algorithm Route Handlers

**File:** `backend/src/api/tax_routes.py`

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.algorithm_service import (
    activate_algorithm,
    get_algorithm,
    list_algorithms,
    register_algorithm,
)
from src.application.tax_service import calculate_tax
from src.domain.schemas import TaxCalculationResult
from src.infrastructure.database import get_db

router = APIRouter(tags=["Tax Calculations"])


# --- Tax Calculation ---

@router.post(
    "/tax/calculate/{user_id}/{year}",
    response_model=TaxCalculationResult,
    summary="Run full tax calculation for a user and year",
)
async def calculate(user_id: str, year: int, db: AsyncSession = Depends(get_db)):
    return await calculate_tax(db, user_id, year)


# --- Algorithm Registry ---

class AlgorithmResponse(BaseModel):
    id: int = Field(description="Algorithm ID")
    function_name: str = Field(description="Name of the calculation function")
    version: str = Field(description="Version string")
    status: str = Field(description="DRAFT, ACTIVE, or ARCHIVED")
    source_law_hash: str | None = Field(description="Hash of the source law text for change detection")

    model_config = {"from_attributes": True}


class AlgorithmCreate(BaseModel):
    function_name: str = Field(description="Name of the calculation function")
    version: str = Field(description="Version string (e.g., '2024.1')")
    code_content: str = Field(description="Python source code of the calculation function")
    source_law_hash: str | None = Field(None, description="Hash of the NTA regulation text")


@router.get("/algorithms", response_model=list[AlgorithmResponse], summary="List all registered algorithms")
async def list_algos(db: AsyncSession = Depends(get_db)):
    return await list_algorithms(db)


@router.get(
    "/algorithms/{function_name}",
    response_model=AlgorithmResponse,
    summary="Get the active version of a specific algorithm",
)
async def get_algo(function_name: str, db: AsyncSession = Depends(get_db)):
    return await get_algorithm(db, function_name)


@router.post("/algorithms", response_model=AlgorithmResponse, status_code=201, summary="Register a new algorithm")
async def register_algo(data: AlgorithmCreate, db: AsyncSession = Depends(get_db)):
    return await register_algorithm(db, data.function_name, data.version, data.code_content, data.source_law_hash)


@router.put(
    "/algorithms/{algorithm_id}/activate",
    response_model=AlgorithmResponse,
    summary="Activate an algorithm version (archives previous active version)",
)
async def activate_algo(algorithm_id: int, db: AsyncSession = Depends(get_db)):
    return await activate_algorithm(db, algorithm_id)
```

**Update `backend/src/main.py`:**

```python
from src.api.tax_routes import router as tax_router

# Inside create_app():
application.include_router(tax_router)
```

### Task 5.6: Unit Tests for Tax Calculations

**File:** `backend/tests/domain/test_tax_calculations.py`

These are **pure unit tests** — no DB, no async, no mocks needed.

```python
from src.domain.tax_calculations import (
    calc_basic_deduction,
    calc_dependents_deduction,
    calc_furusato_limit,
    calc_ideco_deduction,
    calc_income_tax,
    calc_life_insurance_deduction,
    calc_salary_income_deduction,
    calc_social_insurance_deduction,
    calc_spouse_deduction,
    calc_taxable_income,
)


# --- Salary Income Deduction ---

def test_salary_deduction_zero_income():
    assert calc_salary_income_deduction(0) == 0

def test_salary_deduction_low_income():
    assert calc_salary_income_deduction(1_000_000) == 550_000

def test_salary_deduction_mid_income():
    assert calc_salary_income_deduction(5_000_000) == 1_440_000  # 5M * 0.2 + 440K

def test_salary_deduction_high_income_cap():
    assert calc_salary_income_deduction(10_000_000) == 1_950_000


# --- Basic Deduction ---

def test_basic_deduction_standard():
    assert calc_basic_deduction(5_000_000) == 480_000

def test_basic_deduction_high_income_zero():
    assert calc_basic_deduction(26_000_000) == 0


# --- Spouse Deduction ---

def test_spouse_deduction_no_spouse():
    assert calc_spouse_deduction(False, 5_000_000) == 0

def test_spouse_deduction_standard():
    assert calc_spouse_deduction(True, 5_000_000, 0) == 380_000

def test_spouse_deduction_taxpayer_over_limit():
    assert calc_spouse_deduction(True, 11_000_000, 0) == 0


# --- Dependents ---

def test_dependents_zero():
    assert calc_dependents_deduction(0) == 0

def test_dependents_two():
    assert calc_dependents_deduction(2) == 760_000


# --- Social Insurance ---

def test_social_insurance_full_deduction():
    assert calc_social_insurance_deduction(600_000) == 600_000


# --- Life Insurance ---

def test_life_insurance_low():
    assert calc_life_insurance_deduction(15_000) == 15_000

def test_life_insurance_cap():
    assert calc_life_insurance_deduction(100_000) == 40_000


# --- iDeCo ---

def test_ideco_annual():
    assert calc_ideco_deduction(23_000) == 276_000  # 23K * 12


# --- Income Tax ---

def test_income_tax_zero():
    assert calc_income_tax(0) == 0

def test_income_tax_first_bracket():
    assert calc_income_tax(1_000_000) == 50_000  # 1M * 5%

def test_income_tax_second_bracket():
    assert calc_income_tax(3_000_000) == 202_500  # 3M * 10% - 97.5K


# --- Furusato Limit ---

def test_furusato_limit_average_salary():
    limit = calc_furusato_limit(5_000_000, 600_000, False, 0, 0)
    assert limit > 2_000  # Should be a meaningful amount
    assert limit < 200_000  # Sanity check


# --- Taxable Income ---

def test_taxable_income_should_not_be_negative():
    result = calc_taxable_income(0, 0, 0, False, 0, 0)
    assert result == 0
```

### Task 5.7: Integration Tests for Tax Endpoint

**File:** `backend/tests/api/test_tax.py`

```python
async def test_calculate_tax_should_return_result(client):
    # Arrange: create user, income entries, and tax profile
    user_resp = await client.post("/users", json={"display_name": "Tanaka"})
    user_id = user_resp.json()["id"]

    for month in range(1, 13):
        await client.post("/income-entries", json={
            "user_id": user_id,
            "payment_date": f"2024-{month:02d}-25",
            "income_type": "SALARY",
            "gross_amount": 500_000,
        })

    await client.put(f"/tax-profiles/{user_id}/2024", json={
        "has_spouse": True,
        "dependents_count": 1,
        "social_insurance_premium": 600_000,
        "life_insurance_premium": 50_000,
        "ideco_monthly_contribution": 23_000,
    })

    # Act
    response = await client.post(f"/tax/calculate/{user_id}/2024")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["gross_salary"] == 6_000_000
    assert data["income_tax"] > 0
    assert data["furusato_limit"] > 2_000
    assert data["taxable_income"] >= 0


async def test_calculate_tax_no_profile_should_return_404(client):
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]

    response = await client.post(f"/tax/calculate/{user_id}/2024")
    assert response.status_code == 404
    assert response.json()["error_code"] == "TAX_PROFILE_NOT_FOUND"
```

---

## Acceptance Criteria

1. All tax calculation functions in `domain/tax_calculations.py` are pure functions with zero framework imports.
2. `POST /tax/calculate/{user_id}/{year}` returns a full breakdown of deductions, taxable income, income tax, and furusato limit.
3. Tax calculations are deterministic — same input always produces same output.
4. Algorithm Registry supports CRUD: register (DRAFT), list, get active, activate (archives previous).
5. All unit tests for tax calculations pass (covering zero/low/mid/high income, edge cases).
6. Integration test with 12 months of salary produces correct annual totals.
7. `make test` passes all tests.
