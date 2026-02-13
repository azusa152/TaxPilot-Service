"""SQLAlchemy 2.0 ORM models for TaxPilot."""

from datetime import date, datetime
from typing import Any, Optional

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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

from src.domain.enums import AlgorithmStatus, IncomeType


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class User(Base):
    """Root user entity.

    Attributes:
        id: Unique user identifier (UUID string).
        created_at: Timestamp of user creation.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    income_entries: Mapped[list["IncomeEntry"]] = relationship(back_populates="user")
    tax_profiles: Mapped[list["TaxProfile"]] = relationship(back_populates="user")


class IncomeEntry(Base):
    """Monthly financial record for a user.

    Attributes:
        id: Auto-incremented primary key.
        user_id: Foreign key to the user.
        payment_date: Date of payment.
        income_type: Category of income (SALARY, BONUS, OTHER).
        gross_amount: Gross income in JPY.
        social_insurance: Social insurance deduction in JPY.
        withholding_tax: Withholding tax deduction in JPY.
        resident_tax: Resident tax deduction in JPY.
        raw_content: Markdown text extracted by MarkItDown.
    """

    __tablename__ = "income_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    income_type: Mapped[IncomeType] = mapped_column(
        Enum(IncomeType, name="income_type_enum"),
        nullable=False,
    )
    gross_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    social_insurance: Mapped[int] = mapped_column(Integer, default=0)
    withholding_tax: Mapped[int] = mapped_column(Integer, default=0)
    resident_tax: Mapped[int] = mapped_column(Integer, default=0)
    raw_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="income_entries")


class TaxProfile(Base):
    """Annual tax configuration with hybrid SQL+JSONB schema.

    Core fields are stable SQL columns. The additional_attributes JSONB column
    stores dynamic, year-specific tax fields that may change with new tax laws.

    Attributes:
        id: Auto-incremented primary key.
        user_id: Foreign key to the user.
        year: Tax year.
        has_spouse: Whether the user has a spouse for deduction.
        dependents_count: Number of dependents.
        social_insurance_premium: Annual social insurance premium in JPY.
        life_insurance_premium: Annual life insurance premium in JPY.
        ideco_monthly_contribution: Monthly iDeCo contribution in JPY.
        additional_attributes: Dynamic JSONB field for adaptive tax fields.
    """

    __tablename__ = "tax_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    has_spouse: Mapped[bool] = mapped_column(Boolean, default=False)
    dependents_count: Mapped[int] = mapped_column(Integer, default=0)
    social_insurance_premium: Mapped[int] = mapped_column(Integer, default=0)
    life_insurance_premium: Mapped[int] = mapped_column(Integer, default=0)
    ideco_monthly_contribution: Mapped[int] = mapped_column(Integer, default=0)
    additional_attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True, default=dict)

    user: Mapped["User"] = relationship(back_populates="tax_profiles")

    __table_args__ = (Index("ix_tax_profiles_user_year", "user_id", "year", unique=True),)


class ProfileDefinition(Base):
    """Schema definition for a specific tax year.

    Defines what fields are required for a given tax year, enabling
    UI and Agent clients to dynamically render input forms.

    Attributes:
        year: Tax year (primary key).
        schema_definition: JSONB defining required fields for this tax year.
    """

    __tablename__ = "profile_definitions"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    schema_definition: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)


class AlgorithmRegistry(Base):
    """Versioned store for tax calculation algorithms.

    Stores actual Python source code for tax calculation functions,
    enabling hot-reload and version management of tax logic.

    Attributes:
        id: Auto-incremented primary key.
        function_name: Name of the Python function.
        version: Semantic version string.
        code_content: The actual Python source code.
        status: Lifecycle status (DRAFT, ACTIVE, ARCHIVED).
    """

    __tablename__ = "algorithm_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    function_name: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)
    code_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[AlgorithmStatus] = mapped_column(
        Enum(AlgorithmStatus, name="algorithm_status_enum"),
        default=AlgorithmStatus.DRAFT,
    )
