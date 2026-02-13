"""Pydantic v2 request/response schemas for TaxPilot API."""

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.domain.enums import AlgorithmStatus, IncomeType


# --- Income Entry ---


class IncomeEntryCreate(BaseModel):
    """Request schema for creating an income entry."""

    user_id: str = Field(description="User ID who owns this income entry.")
    payment_date: date = Field(description="Date of the payment.")
    income_type: IncomeType = Field(description="Type of income: SALARY, BONUS, or OTHER.")
    gross_amount: int = Field(description="Gross income amount in JPY.")
    social_insurance: int = Field(default=0, description="Social insurance deduction in JPY.")
    withholding_tax: int = Field(default=0, description="Withholding tax deduction in JPY.")
    resident_tax: int = Field(default=0, description="Resident tax deduction in JPY.")
    raw_content: Optional[str] = Field(default=None, description="Markdown content from document ingestion.")


class IncomeEntryResponse(BaseModel):
    """Response schema for an income entry."""

    id: int = Field(description="Unique identifier of the income entry.")
    user_id: str = Field(description="User ID who owns this income entry.")
    payment_date: date = Field(description="Date of the payment.")
    income_type: IncomeType = Field(description="Type of income: SALARY, BONUS, or OTHER.")
    gross_amount: int = Field(description="Gross income amount in JPY.")
    social_insurance: int = Field(description="Social insurance deduction in JPY.")
    withholding_tax: int = Field(description="Withholding tax deduction in JPY.")
    resident_tax: int = Field(description="Resident tax deduction in JPY.")
    raw_content: Optional[str] = Field(default=None, description="Markdown content from document ingestion.")

    model_config = {"from_attributes": True}


# --- Tax Profile ---


class TaxProfileUpdate(BaseModel):
    """Request schema for updating a tax profile (partial update)."""

    has_spouse: Optional[bool] = Field(default=None, description="Whether the user has a spouse.")
    dependents_count: Optional[int] = Field(default=None, description="Number of dependents.")
    social_insurance_premium: Optional[int] = Field(default=None, description="Annual social insurance premium in JPY.")
    life_insurance_premium: Optional[int] = Field(default=None, description="Annual life insurance premium in JPY.")
    ideco_monthly_contribution: Optional[int] = Field(default=None, description="Monthly iDeCo contribution in JPY.")
    additional_attributes: Optional[dict[str, Any]] = Field(
        default=None, description="Dynamic tax-year-specific attributes as key-value pairs."
    )


class TaxProfileResponse(BaseModel):
    """Response schema for a tax profile."""

    id: int = Field(description="Unique identifier of the tax profile.")
    user_id: str = Field(description="User ID who owns this profile.")
    year: int = Field(description="Tax year.")
    has_spouse: bool = Field(description="Whether the user has a spouse.")
    dependents_count: int = Field(description="Number of dependents.")
    social_insurance_premium: int = Field(description="Annual social insurance premium in JPY.")
    life_insurance_premium: int = Field(description="Annual life insurance premium in JPY.")
    ideco_monthly_contribution: int = Field(description="Monthly iDeCo contribution in JPY.")
    additional_attributes: Optional[dict[str, Any]] = Field(
        default=None, description="Dynamic tax-year-specific attributes."
    )

    model_config = {"from_attributes": True}


# --- Profile Definition ---


class ProfileDefinitionResponse(BaseModel):
    """Response schema for a profile definition."""

    year: int = Field(description="Tax year this definition applies to.")
    schema_definition: Optional[dict[str, Any]] = Field(
        default=None, description="JSON schema defining required fields for this tax year."
    )

    model_config = {"from_attributes": True}
