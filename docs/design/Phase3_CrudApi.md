# Phase 3: CRUD API & Schemas
**Goal:** Build the full REST API for all entities with Pydantic v2 schemas, semantic error handling, and comprehensive tests.

**Depends on:** Phase 2 (all 5 models and DB session must be in place)
**Produces:** Complete CRUD endpoints, Pydantic request/response schemas, error handling middleware, schema discovery endpoint

---

## Context

This phase creates the **interface layer** that Agents and UI consume. Every endpoint must be agent-friendly: typed `response_model`, `Field(description=...)` on every field, and semantic error responses with `error_code`.

**Key rules (from `.cursor/rules/ai-agent-friendly.mdc`):**
- Every endpoint has `response_model` and `summary`
- Errors return `{"error_code": "...", "detail": "..."}`
- Schema discovery via `GET /profile-definition/{year}`

---

## Tasks

### Task 3.1: Pydantic Schemas

**File:** `backend/src/domain/schemas.py`

All schemas use Pydantic v2 with `Field(description=...)` for agent readability.

```python
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from src.domain.enums import IncomeType


# --- User ---
class UserCreate(BaseModel):
    display_name: str | None = Field(None, description="Display name of the user")


class UserResponse(BaseModel):
    id: str = Field(description="UUID of the user")
    display_name: str | None = Field(description="Display name of the user")
    created_at: datetime = Field(description="Account creation timestamp (ISO 8601)")

    model_config = {"from_attributes": True}


# --- Income Entry ---
class IncomeEntryCreate(BaseModel):
    user_id: str = Field(description="UUID of the user this entry belongs to")
    payment_date: date = Field(description="Date the payment was received (YYYY-MM-DD)")
    income_type: IncomeType = Field(description="Type of income: SALARY, BONUS, or OTHER")
    gross_amount: int = Field(description="Gross income amount in JPY")
    social_insurance: int = Field(0, description="Social insurance deduction in JPY")
    withholding_tax: int = Field(0, description="Withholding tax deduction in JPY")
    resident_tax: int = Field(0, description="Resident tax deduction in JPY")


class IncomeEntryResponse(BaseModel):
    id: int = Field(description="Income entry ID")
    user_id: str = Field(description="UUID of the user")
    payment_date: date = Field(description="Date the payment was received")
    income_type: IncomeType = Field(description="Type of income")
    gross_amount: int = Field(description="Gross income amount in JPY")
    social_insurance: int = Field(description="Social insurance deduction in JPY")
    withholding_tax: int = Field(description="Withholding tax deduction in JPY")
    resident_tax: int = Field(description="Resident tax deduction in JPY")
    source_file: str | None = Field(description="Path to source document if uploaded")
    raw_content: str | None = Field(description="Markdown content extracted from source document")
    created_at: datetime = Field(description="Entry creation timestamp (ISO 8601)")

    model_config = {"from_attributes": True}


# --- Tax Profile ---
class TaxProfileUpdate(BaseModel):
    has_spouse: bool = Field(False, description="Whether the user has a spouse for tax purposes")
    dependents_count: int = Field(0, description="Number of tax dependents")
    social_insurance_premium: int = Field(0, description="Annual social insurance premium in JPY")
    life_insurance_premium: int = Field(0, description="Annual life insurance premium in JPY")
    ideco_monthly_contribution: int = Field(0, description="Monthly iDeCo contribution in JPY")
    additional_attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Dynamic year-specific fields (e.g., fixed_tax_cut_eligible). See GET /profile-definition/{year} for schema.",
    )


class TaxProfileResponse(BaseModel):
    id: int = Field(description="Tax profile ID")
    user_id: str = Field(description="UUID of the user")
    year: int = Field(description="Tax year")
    has_spouse: bool = Field(description="Whether the user has a spouse")
    dependents_count: int = Field(description="Number of tax dependents")
    social_insurance_premium: int = Field(description="Annual social insurance premium in JPY")
    life_insurance_premium: int = Field(description="Annual life insurance premium in JPY")
    ideco_monthly_contribution: int = Field(description="Monthly iDeCo contribution in JPY")
    additional_attributes: dict[str, Any] = Field(description="Dynamic year-specific tax fields")
    created_at: datetime = Field(description="Profile creation timestamp (ISO 8601)")

    model_config = {"from_attributes": True}


# --- Profile Definition ---
class ProfileDefinitionResponse(BaseModel):
    year: int = Field(description="Tax year this definition applies to")
    schema_definition: dict[str, Any] = Field(
        description="JSON schema defining required/optional fields for this tax year"
    )
    created_at: datetime = Field(description="Definition creation timestamp (ISO 8601)")

    model_config = {"from_attributes": True}
```

### Task 3.2: Error Handling

**File:** `backend/src/api/error_handlers.py`

```python
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.logging_config import get_logger

logger = get_logger(__name__)


class TaxPilotError(Exception):
    """Base exception with error_code for agent-friendly responses."""

    def __init__(self, status_code: int, error_code: str, detail: str):
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(TaxPilotError)
    async def taxpilot_error_handler(request: Request, exc: TaxPilotError):
        logger.warning(f"TaxPilotError: {exc.error_code} - {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"error_code": exc.error_code, "detail": exc.detail},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error_code": "HTTP_ERROR", "detail": str(exc.detail)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        detail = "; ".join(f"{e['loc'][-1]}: {e['msg']}" for e in errors)
        return JSONResponse(
            status_code=422,
            content={"error_code": "VALIDATION_ERROR", "detail": detail},
        )
```

**Update `backend/src/main.py`** to register the error handlers:

```python
from src.api.error_handlers import register_error_handlers

def create_app() -> FastAPI:
    application = FastAPI(...)
    register_error_handlers(application)
    application.include_router(health_router)
    # ... include other routers
    return application
```

### Task 3.3: Application Services

Each service encapsulates the DB operations for one entity. Routes call services, never SQLAlchemy directly.

**File:** `backend/src/application/user_service.py`

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.error_handlers import TaxPilotError
from src.domain.schemas import UserCreate
from src.infrastructure.models import User


async def create_user(db: AsyncSession, data: UserCreate) -> User:
    user = User(display_name=data.display_name)
    db.add(user)
    await db.flush()
    return user


async def get_user(db: AsyncSession, user_id: str) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise TaxPilotError(404, "USER_NOT_FOUND", f"User '{user_id}' not found.")
    return user
```

**File:** `backend/src/application/income_service.py`

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.error_handlers import TaxPilotError
from src.application.user_service import get_user
from src.domain.schemas import IncomeEntryCreate
from src.infrastructure.models import IncomeEntry


async def create_income_entry(db: AsyncSession, data: IncomeEntryCreate) -> IncomeEntry:
    await get_user(db, data.user_id)  # Validate user exists
    entry = IncomeEntry(
        user_id=data.user_id,
        payment_date=data.payment_date,
        income_type=data.income_type.value,
        gross_amount=data.gross_amount,
        social_insurance=data.social_insurance,
        withholding_tax=data.withholding_tax,
        resident_tax=data.resident_tax,
    )
    db.add(entry)
    await db.flush()
    return entry


async def list_income_entries(db: AsyncSession, user_id: str) -> list[IncomeEntry]:
    await get_user(db, user_id)  # Validate user exists
    result = await db.execute(
        select(IncomeEntry).where(IncomeEntry.user_id == user_id).order_by(IncomeEntry.payment_date.desc())
    )
    return list(result.scalars().all())


async def get_income_entry(db: AsyncSession, user_id: str, entry_id: int) -> IncomeEntry:
    result = await db.execute(
        select(IncomeEntry).where(IncomeEntry.user_id == user_id, IncomeEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise TaxPilotError(404, "INCOME_ENTRY_NOT_FOUND", f"Income entry {entry_id} not found for user '{user_id}'.")
    return entry


async def delete_income_entry(db: AsyncSession, user_id: str, entry_id: int) -> None:
    entry = await get_income_entry(db, user_id, entry_id)
    await db.delete(entry)
```

**File:** `backend/src/application/profile_service.py`

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.error_handlers import TaxPilotError
from src.application.user_service import get_user
from src.domain.schemas import TaxProfileUpdate
from src.infrastructure.models import ProfileDefinition, TaxProfile


async def get_or_create_tax_profile(db: AsyncSession, user_id: str, year: int, data: TaxProfileUpdate) -> TaxProfile:
    await get_user(db, user_id)
    result = await db.execute(
        select(TaxProfile).where(TaxProfile.user_id == user_id, TaxProfile.year == year)
    )
    profile = result.scalar_one_or_none()

    if profile is None:
        profile = TaxProfile(user_id=user_id, year=year)
        db.add(profile)

    profile.has_spouse = data.has_spouse
    profile.dependents_count = data.dependents_count
    profile.social_insurance_premium = data.social_insurance_premium
    profile.life_insurance_premium = data.life_insurance_premium
    profile.ideco_monthly_contribution = data.ideco_monthly_contribution
    profile.additional_attributes = data.additional_attributes
    await db.flush()
    return profile


async def get_tax_profile(db: AsyncSession, user_id: str, year: int) -> TaxProfile:
    await get_user(db, user_id)
    result = await db.execute(
        select(TaxProfile).where(TaxProfile.user_id == user_id, TaxProfile.year == year)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise TaxPilotError(
            404, "TAX_PROFILE_NOT_FOUND", f"Tax profile for user '{user_id}', year {year} not found."
        )
    return profile


async def get_profile_definition(db: AsyncSession, year: int) -> ProfileDefinition:
    result = await db.execute(select(ProfileDefinition).where(ProfileDefinition.year == year))
    definition = result.scalar_one_or_none()
    if definition is None:
        raise TaxPilotError(
            404, "PROFILE_DEFINITION_NOT_FOUND", f"Profile definition for year {year} not found."
        )
    return definition
```

### Task 3.4: API Route Handlers

All routes are thin controllers delegating to services.

**File:** `backend/src/api/user_routes.py`

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.user_service import create_user, get_user
from src.domain.schemas import UserCreate, UserResponse
from src.infrastructure.database import get_db

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("", response_model=UserResponse, status_code=201, summary="Create a new user")
async def create_user_endpoint(data: UserCreate, db: AsyncSession = Depends(get_db)):
    user = await create_user(db, data)
    return user


@router.get("/{user_id}", response_model=UserResponse, summary="Get user by ID")
async def get_user_endpoint(user_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_user(db, user_id)
    return user
```

**File:** `backend/src/api/income_routes.py`

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.income_service import (
    create_income_entry,
    delete_income_entry,
    get_income_entry,
    list_income_entries,
)
from src.domain.schemas import IncomeEntryCreate, IncomeEntryResponse
from src.infrastructure.database import get_db

router = APIRouter(prefix="/income-entries", tags=["Income Entries"])


@router.post("", response_model=IncomeEntryResponse, status_code=201, summary="Create a new income entry")
async def create_entry(data: IncomeEntryCreate, db: AsyncSession = Depends(get_db)):
    entry = await create_income_entry(db, data)
    return entry


@router.get("/{user_id}", response_model=list[IncomeEntryResponse], summary="List income entries for a user")
async def list_entries(user_id: str, db: AsyncSession = Depends(get_db)):
    entries = await list_income_entries(db, user_id)
    return entries


@router.get("/{user_id}/{entry_id}", response_model=IncomeEntryResponse, summary="Get a single income entry")
async def get_entry(user_id: str, entry_id: int, db: AsyncSession = Depends(get_db)):
    entry = await get_income_entry(db, user_id, entry_id)
    return entry


@router.delete("/{user_id}/{entry_id}", status_code=204, summary="Delete an income entry")
async def delete_entry(user_id: str, entry_id: int, db: AsyncSession = Depends(get_db)):
    await delete_income_entry(db, user_id, entry_id)
```

**File:** `backend/src/api/profile_routes.py`

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.profile_service import (
    get_or_create_tax_profile,
    get_profile_definition,
    get_tax_profile,
)
from src.domain.schemas import ProfileDefinitionResponse, TaxProfileResponse, TaxProfileUpdate
from src.infrastructure.database import get_db

router = APIRouter(tags=["Tax Profiles"])


@router.get(
    "/tax-profiles/{user_id}/{year}",
    response_model=TaxProfileResponse,
    summary="Get annual tax profile",
)
async def get_profile(user_id: str, year: int, db: AsyncSession = Depends(get_db)):
    profile = await get_tax_profile(db, user_id, year)
    return profile


@router.put(
    "/tax-profiles/{user_id}/{year}",
    response_model=TaxProfileResponse,
    summary="Create or update annual tax profile",
)
async def upsert_profile(
    user_id: str, year: int, data: TaxProfileUpdate, db: AsyncSession = Depends(get_db)
):
    profile = await get_or_create_tax_profile(db, user_id, year, data)
    return profile


@router.get(
    "/profile-definition/{year}",
    response_model=ProfileDefinitionResponse,
    summary="Schema discovery: get required fields for a tax year",
)
async def get_definition(year: int, db: AsyncSession = Depends(get_db)):
    definition = await get_profile_definition(db, year)
    return definition
```

**Update `backend/src/main.py`** to register all routers:

```python
from src.api.health_routes import router as health_router
from src.api.user_routes import router as user_router
from src.api.income_routes import router as income_router
from src.api.profile_routes import router as profile_router

def create_app() -> FastAPI:
    # ...
    application.include_router(health_router)
    application.include_router(user_router)
    application.include_router(income_router)
    application.include_router(profile_router)
    return application
```

### Task 3.5: Tests

Tests should cover happy path, validation error (422), not found (404), and conflict (409 where applicable) for each endpoint.

**File:** `backend/tests/api/test_users.py`

```python
async def test_create_user_should_return_201(client):
    response = await client.post("/users", json={"display_name": "Tanaka"})
    assert response.status_code == 201
    data = response.json()
    assert data["display_name"] == "Tanaka"
    assert "id" in data


async def test_get_user_not_found_should_return_404(client):
    response = await client.get("/users/nonexistent-id")
    assert response.status_code == 404
    assert response.json()["error_code"] == "USER_NOT_FOUND"
```

**File:** `backend/tests/api/test_income_entries.py`

```python
async def test_create_income_entry_should_return_201(client):
    # Arrange: create a user first
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]

    # Act
    response = await client.post("/income-entries", json={
        "user_id": user_id,
        "payment_date": "2024-01-25",
        "income_type": "SALARY",
        "gross_amount": 500000,
        "social_insurance": 40000,
        "withholding_tax": 15000,
    })

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["gross_amount"] == 500000
    assert data["income_type"] == "SALARY"


async def test_create_income_entry_invalid_type_should_return_422(client):
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]

    response = await client.post("/income-entries", json={
        "user_id": user_id,
        "payment_date": "2024-01-25",
        "income_type": "INVALID",
        "gross_amount": 500000,
    })
    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"


async def test_list_income_entries_for_nonexistent_user_should_return_404(client):
    response = await client.get("/income-entries/nonexistent-id")
    assert response.status_code == 404


async def test_delete_income_entry_should_return_204(client):
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]
    entry_resp = await client.post("/income-entries", json={
        "user_id": user_id,
        "payment_date": "2024-06-15",
        "income_type": "BONUS",
        "gross_amount": 1000000,
    })
    entry_id = entry_resp.json()["id"]

    response = await client.delete(f"/income-entries/{user_id}/{entry_id}")
    assert response.status_code == 204
```

**File:** `backend/tests/api/test_profiles.py`

```python
async def test_upsert_tax_profile_should_return_200(client):
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]

    response = await client.put(f"/tax-profiles/{user_id}/2024", json={
        "has_spouse": True,
        "dependents_count": 2,
        "social_insurance_premium": 600000,
        "additional_attributes": {"fixed_tax_cut_eligible": True},
    })
    assert response.status_code == 200
    data = response.json()
    assert data["has_spouse"] is True
    assert data["additional_attributes"]["fixed_tax_cut_eligible"] is True


async def test_get_tax_profile_not_found_should_return_404(client):
    user_resp = await client.post("/users", json={"display_name": "Test"})
    user_id = user_resp.json()["id"]

    response = await client.get(f"/tax-profiles/{user_id}/2024")
    assert response.status_code == 404
    assert response.json()["error_code"] == "TAX_PROFILE_NOT_FOUND"


async def test_get_profile_definition_not_found_should_return_404(client):
    response = await client.get("/profile-definition/9999")
    assert response.status_code == 404
    assert response.json()["error_code"] == "PROFILE_DEFINITION_NOT_FOUND"
```

**Note:** `conftest.py` will need to be updated for Phase 3 to provide a test database (either test PostgreSQL or in-memory SQLite with async) so CRUD operations actually persist and query correctly.

---

## Acceptance Criteria

1. All CRUD endpoints return correct status codes (201, 200, 204, 404, 422).
2. Error responses always include `error_code` and `detail` fields.
3. `GET /profile-definition/{year}` returns the schema discovery JSONB.
4. `PUT /tax-profiles/{user_id}/{year}` is idempotent (upsert behavior).
5. `GET http://localhost:8000/openapi.json` has full schemas with descriptions for all endpoints.
6. `GET http://localhost:8000/docs` shows all endpoints in Swagger UI.
7. `make test` passes all tests.
