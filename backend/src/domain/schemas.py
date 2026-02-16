from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from src.domain.enums import IncomeType, LawChangeType, LlmProvider, ReviewDecision, VerificationStatus


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


# --- Regulation Parser (Phase 6C) ---
class LawChange(BaseModel):
    """A single identified change in tax regulations.

    Used as part of the LLM response_format for structured output.
    The LawChangeType enum constrains the JSON schema sent to the LLM,
    ensuring it only returns valid change types.
    """

    change_type: LawChangeType = Field(
        description="Type of tax law change identified"
    )
    affected_function: str = Field(
        description="Name of the tax calculation function affected "
        "(e.g., 'calc_income_tax', 'calc_salary_income_deduction')"
    )
    old_value: str = Field(
        description="Previous value or rule (use 'N/A' for new additions)"
    )
    new_value: str = Field(
        description="New value or rule being introduced"
    )
    description: str = Field(
        description="Human-readable description of the change in English"
    )
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="LLM confidence in this change identification (0.0 to 1.0)",
    )


class RegulationAnalysis(BaseModel):
    """Structured analysis of NTA regulation changes.

    Returned by the RegulationParser. Used as LLM response_format.
    """

    changes: list[LawChange] = Field(
        description="List of identified law changes"
    )
    summary: str = Field(
        description="Brief summary of all changes found in this regulation update"
    )
    tax_year: int = Field(
        description="The tax year these changes apply to"
    )
    no_changes_detected: bool = Field(
        default=False,
        description="True if the page content changed but no tax rule changes were found "
        "(e.g., only formatting or navigation changes)",
    )


# --- Code & Schema Generator (Phase 6D) ---
class CodeGenerationResult(BaseModel):
    """Structured result from LLM code generation.

    Used as response_format for LiteLLM structured output.
    """

    function_name: str = Field(
        description="Name of the generated calculation function "
        "(must match the existing function name being updated)"
    )
    version: str = Field(
        description="Version string for this algorithm (e.g., '2025.1')"
    )
    code_content: str = Field(
        description="Complete Python source code of the updated function. "
        "Must be a pure function with no imports, no side effects, no I/O."
    )
    description: str = Field(
        description="Human-readable description of what changed and why"
    )
    referenced_regulation: str = Field(
        description="The specific NTA regulation or page section that this code implements"
    )


class FieldDefinition(BaseModel):
    """Definition of a single field in the ProfileDefinition schema."""

    name: str = Field(description="Field name (snake_case)")
    type: str = Field(
        description="Python type string: 'int', 'float', 'bool', 'str'"
    )
    required: bool = Field(description="Whether this field is required")
    description: str = Field(
        description="Human-readable description of the field (in English)"
    )
    description_ja: str = Field(
        description="Japanese description of the field for UI display"
    )
    default_value: str | None = Field(
        None,
        description="Default value as a string (e.g., '0', 'false'). None if required with no default.",
    )


class SchemaChangeProposal(BaseModel):
    """Proposed changes to the ProfileDefinition schema.

    Used as response_format for LiteLLM structured output.
    """

    year: int = Field(description="Tax year this schema change applies to")
    new_fields: list[FieldDefinition] = Field(
        description="New fields to add to the ProfileDefinition"
    )
    removed_fields: list[str] = Field(
        description="Field names to remove (empty list if none)"
    )
    modified_fields: list[FieldDefinition] = Field(
        default_factory=list,
        description="Fields with updated definitions (e.g., changed type or description)",
    )
    change_rationale: str = Field(
        description="Explanation of why these schema changes are needed"
    )


# --- Bootstrap & Verification (Phase 6-Pre) ---
class VerificationResult(BaseModel):
    """Result of verifying a single formula against NTA text.

    Used as LLM response_format for structured verification output.
    """

    function_name: str = Field(
        description="Name of the tax calculation function being verified"
    )
    status: VerificationStatus = Field(
        description="Verification result: MATCH, MISMATCH, or PARTIAL"
    )
    extracted_thresholds: list[dict] = Field(
        description="Tax thresholds/rates extracted from the NTA text by the LLM. "
        "Each entry: {bracket: str, threshold: int, rate_or_amount: str}"
    )
    hardcoded_comparison: str = Field(
        description="Line-by-line comparison of LLM-extracted rules vs hardcoded logic"
    )
    discrepancies: list[str] = Field(
        description="List of specific discrepancies found (empty if MATCH)"
    )
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the verification result",
    )
    summary: str = Field(
        description="Brief summary of the verification in English"
    )


class BootstrapReport(BaseModel):
    """Overall bootstrap verification report."""

    total_functions: int = Field(description="Total functions verified")
    matched: int = Field(description="Number of functions that match NTA text")
    mismatched: int = Field(description="Number of functions with mismatches")
    partial: int = Field(description="Number of partial matches")
    results: list[VerificationResult] = Field(
        description="Per-function verification results"
    )
    bootstrap_completed_at: datetime


# --- Phase 6E: Evolution Pipeline Review ---
class ReviewRequest(BaseModel):
    """Admin review decision for an evolution run."""

    decision: ReviewDecision = Field(
        description="Review decision: ACCEPT, MODIFY, REGENERATE, SKIP_PERMANENT, SKIP_MANUAL"
    )
    rationale: str = Field(
        description="Reason for the decision (required for all decisions)"
    )
    modified_code: str | None = Field(
        None,
        description="Admin-provided code (required when decision=MODIFY)"
    )
    regeneration_hints: str | None = Field(
        None,
        description="Hints for the LLM to improve generation (optional, used when decision=REGENERATE)"
    )
    skip_reason: str | None = Field(
        None,
        description="Reason for skipping (optional, used when decision=SKIP_*)"
    )


class EvolutionRunDetail(BaseModel):
    """Detailed view of an evolution run including generated artifacts."""

    id: int
    trigger: str
    status: str
    nta_snapshot_id: int | None
    parsed_changes: dict | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
    review_decision: str | None
    rationale: str | None
    regeneration_count: int
    max_regenerations: int
    generation_attempts: list[dict] = Field(
        default_factory=list,
        description="All code generation attempts for this run"
    )
    schema_proposal: dict | None = Field(
        None, description="Proposed schema changes (if any)"
    )

    model_config = {"from_attributes": True}


class EvolutionRunSummary(BaseModel):
    """Summary view of an evolution run for list endpoints."""

    id: int
    trigger: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    review_decision: str | None

    model_config = {"from_attributes": True}
