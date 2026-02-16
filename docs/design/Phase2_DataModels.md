# Phase 2: Data Models & Database
**Goal:** Create all 5 SQLAlchemy models, set up Alembic async migrations, and establish the database session layer.

**Depends on:** Phase 1 (Docker + project skeleton must be running)
**Produces:** 5 database tables, Alembic migration pipeline, domain enums/constants, DB session factory

---

## Context

TaxPilot uses a **hybrid schema** approach: stable relational fields live as SQL columns, while year-specific adaptive fields live in JSONB. This phase creates the data layer that all API endpoints (Phase 3) and business logic (Phase 5) depend on.

**Key entities from the PRD:**
- **User** — root entity
- **IncomeEntry** — monthly financial records
- **TaxProfile** — annual tax settings (SQL + JSONB)
- **ProfileDefinition** — schema discovery metadata
- **AlgorithmRegistry** — versioned calculation logic

---

## Tasks

### Task 2.1: Domain Enums

**File:** `backend/src/domain/enums.py`

```python
from enum import Enum


class IncomeType(str, Enum):
    SALARY = "SALARY"
    BONUS = "BONUS"
    OTHER = "OTHER"


class AlgorithmStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
```

Using `str, Enum` so values serialize cleanly to JSON and work with Pydantic v2.

### Task 2.2: Domain Constants

**File:** `backend/src/domain/constants.py`

```python
# Tax year defaults
DEFAULT_TAX_YEAR = 2024

# Income thresholds (JPY)
BASIC_DEDUCTION = 480_000
SALARY_DEDUCTION_MIN = 550_000

# Furusato Nouzei
FURUSATO_SELF_BURDEN = 2_000

# Profile Definition — 2024 default schema
PROFILE_DEFINITION_2024 = {
    "year": 2024,
    "fields": [
        {"name": "fixed_tax_cut_eligible", "type": "boolean", "required": True, "description": "2024 Fixed Tax Cut eligibility"},
        {"name": "fixed_tax_cut_dependents", "type": "integer", "required": False, "description": "Number of dependents for Fixed Tax Cut"},
    ],
}
```

These constants will grow as tax calculations are implemented in Phase 5.

### Task 2.3: SQLAlchemy Models

**File:** `backend/src/infrastructure/models.py`

Use SQLAlchemy 2.0 style with `Mapped` / `mapped_column`:

```python
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    income_entries: Mapped[list["IncomeEntry"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    tax_profiles: Mapped[list["TaxProfile"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class IncomeEntry(Base):
    __tablename__ = "income_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    income_type: Mapped[str] = mapped_column(Enum("SALARY", "BONUS", "OTHER", name="income_type_enum"), nullable=False)
    gross_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    social_insurance: Mapped[int] = mapped_column(Integer, default=0)
    withholding_tax: Mapped[int] = mapped_column(Integer, default=0)
    resident_tax: Mapped[int] = mapped_column(Integer, default=0)
    source_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="income_entries")

    __table_args__ = (
        Index("ix_income_entries_user_date", "user_id", "payment_date"),
    )


class TaxProfile(Base):
    __tablename__ = "tax_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)

    # Core stable fields
    has_spouse: Mapped[bool] = mapped_column(Boolean, default=False)
    dependents_count: Mapped[int] = mapped_column(Integer, default=0)
    social_insurance_premium: Mapped[int] = mapped_column(Integer, default=0)
    life_insurance_premium: Mapped[int] = mapped_column(Integer, default=0)
    ideco_monthly_contribution: Mapped[int] = mapped_column(Integer, default=0)

    # Dynamic adaptive fields
    additional_attributes: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="tax_profiles")

    __table_args__ = (
        UniqueConstraint("user_id", "year", name="uq_tax_profile_user_year"),
        Index("ix_tax_profiles_user_year", "user_id", "year"),
    )


class ProfileDefinition(Base):
    __tablename__ = "profile_definitions"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    schema_definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AlgorithmRegistry(Base):
    __tablename__ = "algorithm_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    function_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    code_content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("DRAFT", "ACTIVE", "ARCHIVED", name="algorithm_status_enum"),
        default="DRAFT",
    )
    source_law_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("function_name", "version", name="uq_algorithm_func_version"),
        Index("ix_algorithm_func_version", "function_name", "version"),
    )
```

### Task 2.4: Database Session Factory

**File:** `backend/src/infrastructure/database.py`

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

`get_db()` is the FastAPI `Depends()` provider. Sessions auto-commit on success and rollback on exception.

### Task 2.5: Update Health Endpoint

Update `backend/src/api/health_routes.py` to test actual DB connectivity:

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database import get_db
from src.logging_config import get_logger

router = APIRouter(tags=["Health"])
logger = get_logger(__name__)


class HealthResponse(BaseModel):
    status: str = Field(description="Service health status")
    database: str = Field(description="Database connectivity status")


@router.get("/health", response_model=HealthResponse, summary="Check service health")
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "disconnected"

    status = "healthy" if db_status == "connected" else "degraded"
    return HealthResponse(status=status, database=db_status)
```

### Task 2.6: Alembic Setup

Initialize Alembic with async template:

```bash
cd backend
alembic init -t async alembic
```

**Edit `backend/alembic/env.py`** to import models and use the async engine:

Key changes to the generated `env.py`:
1. Import `Base` from `src.infrastructure.models`
2. Import `settings` from `src.config`
3. Set `target_metadata = Base.metadata`
4. Set `config.set_main_option("sqlalchemy.url", settings.database_url)`

**Edit `backend/alembic.ini`:**
- Set `script_location = alembic`
- The `sqlalchemy.url` will be overridden by `env.py` from settings.

**Generate initial migration:**

```bash
alembic revision --autogenerate -m "create initial tables"
```

This should produce a migration creating all 5 tables: `users`, `income_entries`, `tax_profiles`, `profile_definitions`, `algorithm_registry`.

### Task 2.7: Seed Script

**File:** `backend/src/infrastructure/seed.py`

```python
"""Seed initial data for development."""
import asyncio

from sqlalchemy import select

from src.domain.constants import PROFILE_DEFINITION_2024
from src.infrastructure.database import async_session_factory
from src.infrastructure.models import ProfileDefinition
from src.logging_config import get_logger

logger = get_logger(__name__)


async def seed_profile_definitions():
    async with async_session_factory() as session:
        existing = await session.execute(
            select(ProfileDefinition).where(ProfileDefinition.year == 2024)
        )
        if existing.scalar_one_or_none() is None:
            definition = ProfileDefinition(
                year=2024,
                schema_definition=PROFILE_DEFINITION_2024,
            )
            session.add(definition)
            await session.commit()
            logger.info("Seeded ProfileDefinition for 2024")
        else:
            logger.info("ProfileDefinition for 2024 already exists, skipping")


async def run_seed():
    await seed_profile_definitions()


if __name__ == "__main__":
    asyncio.run(run_seed())
```

Run via: `docker-compose run --rm api python -m src.infrastructure.seed`

### Task 2.8: Tests

**File:** `backend/tests/infrastructure/test_models.py`

```python
from src.infrastructure.models import (
    AlgorithmRegistry,
    IncomeEntry,
    ProfileDefinition,
    TaxProfile,
    User,
)


def test_user_model_should_have_correct_tablename():
    assert User.__tablename__ == "users"


def test_income_entry_should_have_user_foreign_key():
    columns = {c.name for c in IncomeEntry.__table__.columns}
    assert "user_id" in columns
    assert "gross_amount" in columns
    assert "raw_content" in columns


def test_tax_profile_should_have_jsonb_column():
    col = TaxProfile.__table__.columns["additional_attributes"]
    assert col is not None


def test_profile_definition_should_have_year_as_pk():
    pk_cols = [c.name for c in ProfileDefinition.__table__.primary_key.columns]
    assert pk_cols == ["year"]


def test_algorithm_registry_should_have_unique_func_version():
    constraints = [c.name for c in AlgorithmRegistry.__table__.constraints if hasattr(c, "name") and c.name]
    assert "uq_algorithm_func_version" in constraints
```

---

## Acceptance Criteria

1. `alembic upgrade head` creates all 5 tables in PostgreSQL without errors.
2. `TaxProfile` table has a working JSONB column (`additional_attributes`).
3. `ProfileDefinition` table has a JSONB column (`schema_definition`).
4. `AlgorithmRegistry` has a unique constraint on `(function_name, version)`.
5. `GET /health` now returns `{"status": "healthy", "database": "connected"}` when DB is reachable.
6. Seed script successfully inserts the 2024 ProfileDefinition.
7. `make test` passes all model tests.
