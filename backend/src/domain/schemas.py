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
