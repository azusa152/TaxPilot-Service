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
