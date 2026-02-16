from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.income_service import (
    create_income_entry,
    delete_income_entry,
    get_income_entry,
    list_income_entries,
)
from src.domain.schemas import IncomeEntryCreate, IncomeEntryResponse
from src.infrastructure.database import get_db

router = APIRouter(prefix="/income-entries", tags=["Income Entries"])


@router.post("", response_model=IncomeEntryResponse, status_code=201, summary="Create a new income entry")
async def create_entry(data: IncomeEntryCreate, db: AsyncSession = Depends(get_db)):
    entry = await create_income_entry(db, data)
    return entry


@router.get("/{user_id}", response_model=list[IncomeEntryResponse], summary="List income entries for a user")
async def list_entries(user_id: str, db: AsyncSession = Depends(get_db)):
    entries = await list_income_entries(db, user_id)
    return entries


@router.get("/{user_id}/{entry_id}", response_model=IncomeEntryResponse, summary="Get a single income entry")
async def get_entry(user_id: str, entry_id: int, db: AsyncSession = Depends(get_db)):
    entry = await get_income_entry(db, user_id, entry_id)
    return entry


@router.delete("/{user_id}/{entry_id}", status_code=204, summary="Delete an income entry")
async def delete_entry(user_id: str, entry_id: int, db: AsyncSession = Depends(get_db)):
    await delete_income_entry(db, user_id, entry_id)
