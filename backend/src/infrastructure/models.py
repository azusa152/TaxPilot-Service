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

from src.domain.enums import EvolutionRunStatus, ProposalStatus


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


class EvolutionRun(Base):
    """Tracks an end-to-end evolution pipeline run.

    Status progression: PENDING → CRAWLING → PARSING → GENERATING →
    AWAITING_REVIEW → ACCEPTED / MODIFIED / REGENERATING / SKIPPED / DEFERRED / FAILED
    """

    __tablename__ = "evolution_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)  # CrawlerRunTrigger
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=EvolutionRunStatus.PENDING
    )
    nta_snapshot_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("nta_page_snapshots.id"), nullable=True
    )
    parsed_changes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # TODO(Phase 6E): Add review_decision, rationale, modified_code,
    # regeneration_hints, regeneration_count, max_regenerations fields
    # for the admin review workflow.

    __table_args__ = (
        Index("ix_evolution_runs_status", "status"),
        Index("ix_evolution_runs_started_at", "started_at"),
    )


class LlmUsageLog(Base):
    """Tracks token usage and cost for each LLM call."""

    __tablename__ = "llm_usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    evolution_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("evolution_runs.id"), nullable=True
    )
    caller: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_llm_usage_logs_created_at", "created_at"),
        Index("ix_llm_usage_logs_evolution_run_id", "evolution_run_id"),
    )


class NtaTargetPage(Base):
    """Configurable list of NTA pages to monitor."""

    __tablename__ = "nta_target_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    check_interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    snapshots: Mapped[list["NtaPageSnapshot"]] = relationship(
        back_populates="target_page", order_by="desc(NtaPageSnapshot.fetched_at)"
    )


class NtaCrawlerRun(Base):
    """Records each crawler run (manual or scheduled)."""

    __tablename__ = "nta_crawler_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pages_checked: Mapped[int] = mapped_column(Integer, default=0)
    pages_changed: Mapped[int] = mapped_column(Integer, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (Index("ix_nta_crawler_runs_started_at", "started_at"),)


class NtaPageSnapshot(Base):
    """Stores a point-in-time snapshot of an NTA page.

    Crawl4AI CrawlResult provides raw_markdown and fit_markdown
    for full and LLM-optimized markdown respectively.
    """

    __tablename__ = "nta_page_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_page_id: Mapped[int] = mapped_column(Integer, ForeignKey("nta_target_pages.id"), nullable=False)
    crawler_run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("nta_crawler_runs.id"), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    fit_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_tables: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="SUCCESS")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    target_page: Mapped["NtaTargetPage"] = relationship(back_populates="snapshots")

    __table_args__ = (
        Index("ix_nta_snapshots_target_fetched", "target_page_id", "fetched_at"),
        Index("ix_nta_snapshots_content_hash", "content_hash"),
    )


class SchemaChangeProposalRecord(Base):
    """Stores proposed schema changes linked to an evolution run."""

    __tablename__ = "schema_change_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evolution_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("evolution_runs.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    proposal_data: Mapped[dict] = mapped_column(
        JSONB, nullable=False
    )  # Serialized SchemaChangeProposal
    status: Mapped[str] = mapped_column(
        String(20), default=ProposalStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_schema_change_proposals_evolution_run_id", "evolution_run_id"),
        Index("ix_schema_change_proposals_year", "year"),
    )


class GenerationAttempt(Base):
    """Tracks each code generation attempt within an evolution run.

    Supports the REGENERATE flow where admin requests re-generation with hints.
    """

    __tablename__ = "generation_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evolution_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("evolution_runs.id"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_code: Mapped[str] = mapped_column(Text, nullable=False)
    generated_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    validation_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    validation_errors: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    admin_hints: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Hints provided by admin for regeneration
    # TODO: Populate from LlmService usage log. Cost data currently lives
    # only in LlmUsageLog; this field is reserved for denormalized access.
    llm_cost_usd: Mapped[float | None] = mapped_column(
        Numeric(10, 6), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_generation_attempts_evolution_run_id", "evolution_run_id"),
    )
