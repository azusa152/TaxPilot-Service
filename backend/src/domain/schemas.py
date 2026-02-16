from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from src.domain.enums import IncomeType, LlmProvider


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
    payment_date: date | None = Field(description="Date the payment was received (null if pending extraction)")
    income_type: IncomeType = Field(description="Type of income")
    gross_amount: int = Field(description="Gross income amount in JPY")
    social_insurance: int = Field(description="Social insurance deduction in JPY")
    withholding_tax: int = Field(description="Withholding tax deduction in JPY")
    resident_tax: int = Field(description="Resident tax deduction in JPY")
    source_file: str | None = Field(description="Path to source document if uploaded")
    raw_content: str | None = Field(description="Markdown content extracted from source document")
    created_at: datetime = Field(description="Entry creation timestamp (ISO 8601)")

    model_config = {"from_attributes": True}


# --- Algorithm Registry ---
class AlgorithmCreate(BaseModel):
    function_name: str = Field(description="Name of the calculation function")
    version: str = Field(description="Version string (e.g., '2024.1')")
    code_content: str = Field(description="Python source code of the calculation function")
    source_law_hash: str | None = Field(None, description="Hash of the NTA regulation text")


class AlgorithmResponse(BaseModel):
    id: int = Field(description="Algorithm ID")
    function_name: str = Field(description="Name of the calculation function")
    version: str = Field(description="Version string")
    status: str = Field(description="DRAFT, ACTIVE, or ARCHIVED")
    source_law_hash: str | None = Field(description="Hash of the source law text for change detection")

    model_config = {"from_attributes": True}


# --- Tax Calculation ---
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


# --- Tax Profile ---
class TaxProfileUpdate(BaseModel):
    has_spouse: bool = Field(False, description="Whether the user has a spouse for tax purposes")
    dependents_count: int = Field(0, description="Number of tax dependents")
    social_insurance_premium: int = Field(0, description="Annual social insurance premium in JPY")
    life_insurance_premium: int = Field(0, description="Annual life insurance premium in JPY")
    ideco_monthly_contribution: int = Field(0, description="Monthly iDeCo contribution in JPY")
    additional_attributes: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Dynamic year-specific fields (e.g., fixed_tax_cut_eligible)."
            " See GET /profile-definition/{year} for schema."
        ),
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


# --- LLM Configuration (Phase 6A) ---
class LlmConfigCreate(BaseModel):
    """Request schema for creating/updating LLM provider configuration."""

    provider: LlmProvider = Field(description="LLM provider name (gemini, openai, anthropic)")
    model_name: str = Field(description="LiteLLM model string (e.g., 'openai/gpt-4o')")
    api_token: str = Field(description="API token for the provider (will be encrypted at rest)")
    monthly_budget_usd: float = Field(
        default=50.00,
        description="Monthly budget cap in USD. Calls are rejected when exceeded.",
    )


class LlmConfigResponse(BaseModel):
    """Response schema for LLM provider configuration (token masked)."""

    id: int = Field(description="Config ID")
    provider: str = Field(description="LLM provider name")
    model_name: str = Field(description="LiteLLM model string")
    masked_token: str = Field(description="Masked API token (e.g., 'sk-...a3f2')")
    is_active: bool = Field(description="Whether this config is the active one")
    monthly_budget_usd: float = Field(description="Monthly budget cap in USD")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LlmUsageSummary(BaseModel):
    """Summary of LLM usage and costs."""

    total_calls: int = Field(description="Total number of LLM calls")
    total_prompt_tokens: int = Field(description="Total prompt tokens used")
    total_completion_tokens: int = Field(description="Total completion tokens used")
    total_cost_usd: float = Field(description="Total cost in USD")
    daily_breakdown: list[dict] = Field(description="Cost breakdown by day [{date, calls, cost_usd}]")
    monthly_total_usd: float = Field(description="Total cost for the current month")
    budget_remaining_usd: float = Field(description="Remaining budget for the current month")


# --- NTA Crawler (Phase 6B) ---
class NtaTargetPageConfig(BaseModel):
    """Schema for creating/updating a target NTA page."""

    name: str = Field(description="Short name for the page (e.g., 'income_tax_rates')")
    url: str = Field(description="Full URL of the NTA page")
    description: str | None = Field(None, description="Description of what this page contains")
    is_active: bool = Field(default=True, description="Whether to actively monitor this page")
    check_interval_hours: int = Field(default=24, description="How often to check this page (in hours)")


class NtaPageChange(BaseModel):
    """Represents a detected change on an NTA page."""

    page_name: str = Field(description="Name of the NTA target page")
    page_url: str = Field(description="URL of the NTA page")
    previous_hash: str | None = Field(description="Content hash of the previous snapshot")
    new_hash: str = Field(description="Content hash of the new snapshot")
    snapshot_id: int = Field(description="ID of the new snapshot")


class NtaSnapshotDetail(BaseModel):
    """Detailed view of a single snapshot including markdown content."""

    id: int = Field(description="Snapshot ID")
    target_page_name: str = Field(description="Name of the monitored page")
    target_page_url: str = Field(description="URL of the monitored page")
    content_hash: str = Field(description="SHA-256 hash of fit_markdown")
    raw_markdown: str | None = Field(description="Full page as markdown")
    fit_markdown: str | None = Field(description="LLM-optimized markdown (boilerplate removed)")
    extracted_tables: dict | None = Field(description="Structured table data as JSON")
    status: str = Field(description="SUCCESS / FAILED / TIMEOUT")
    error_message: str | None = Field(description="Error message if status is FAILED/TIMEOUT")
    response_time_ms: int | None = Field(description="Response time in milliseconds")
    fetched_at: datetime

    model_config = {"from_attributes": True}


class CrawlerRunSummary(BaseModel):
    """Summary of a single crawler run."""

    id: int = Field(description="Run ID")
    trigger: str = Field(description="MANUAL or SCHEDULED")
    started_at: datetime
    completed_at: datetime | None
    pages_checked: int
    pages_changed: int
    pages_failed: int

    model_config = {"from_attributes": True}


class CrawlerHealthStatus(BaseModel):
    """Overall health status of the crawler."""

    status: str = Field(description="Health indicator: 'healthy' (green), 'degraded' (yellow), 'error' (red)")
    last_run: CrawlerRunSummary | None = Field(description="Most recent crawler run")
    next_scheduled_run: datetime | None = Field(description="Next scheduled crawl time")
    total_target_pages: int = Field(description="Total number of monitored pages")
    active_target_pages: int = Field(description="Number of actively monitored pages")
