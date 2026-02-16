from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.user_service import get_user
from src.domain.exceptions import TaxPilotError
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
