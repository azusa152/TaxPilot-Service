from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.user_service import get_user
from src.domain.exceptions import TaxPilotError
from src.domain.schemas import IncomeEntryCreate
from src.infrastructure.models import IncomeEntry


async def create_income_entry(db: AsyncSession, data: IncomeEntryCreate) -> IncomeEntry:
    await get_user(db, data.user_id)
    entry = IncomeEntry(
        user_id=data.user_id,
        payment_date=data.payment_date,
        income_type=data.income_type.value,
        gross_amount=data.gross_amount,
        social_insurance=data.social_insurance,
        withholding_tax=data.withholding_tax,
        resident_tax=data.resident_tax,
    )
    db.add(entry)
    await db.flush()
    return entry


async def list_income_entries(db: AsyncSession, user_id: str) -> list[IncomeEntry]:
    await get_user(db, user_id)
    result = await db.execute(
        select(IncomeEntry).where(IncomeEntry.user_id == user_id).order_by(IncomeEntry.payment_date.desc())
    )
    return list(result.scalars().all())


async def get_income_entry(db: AsyncSession, user_id: str, entry_id: int) -> IncomeEntry:
    result = await db.execute(
        select(IncomeEntry).where(IncomeEntry.user_id == user_id, IncomeEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise TaxPilotError(404, "INCOME_ENTRY_NOT_FOUND", f"Income entry {entry_id} not found for user '{user_id}'.")
    return entry


async def delete_income_entry(db: AsyncSession, user_id: str, entry_id: int) -> None:
    entry = await get_income_entry(db, user_id, entry_id)
    await db.delete(entry)
