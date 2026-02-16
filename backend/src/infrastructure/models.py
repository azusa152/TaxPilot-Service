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
    Numeric,
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
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
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


class LlmProviderConfig(Base):
    """Stores LLM provider configuration with encrypted API tokens."""

    __tablename__ = "llm_provider_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    encrypted_api_token: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    monthly_budget_usd: Mapped[float] = mapped_column(Numeric(10, 2), default=50.00)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("ix_llm_provider_configs_provider_active", "provider", "is_active"),)


class LlmUsageLog(Base):
    """Tracks token usage and cost for each LLM call."""

    __tablename__ = "llm_usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    # TODO(Phase 6E): Add ForeignKey("evolution_runs.id") once the table exists
    evolution_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    caller: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_llm_usage_logs_created_at", "created_at"),
        Index("ix_llm_usage_logs_evolution_run_id", "evolution_run_id"),
    )
