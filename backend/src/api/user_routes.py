from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.user_service import create_user, get_user, update_user
from src.domain.schemas import UserCreate, UserResponse, UserUpdate
from src.infrastructure.database import get_db

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("", response_model=UserResponse, status_code=201, summary="Create a new user")
async def create_user_endpoint(data: UserCreate, db: AsyncSession = Depends(get_db)):
    user = await create_user(db, data)
    return user


@router.get("/{user_id}", response_model=UserResponse, summary="Get user by ID")
async def get_user_endpoint(user_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_user(db, user_id)
    return user


@router.patch("/{user_id}", response_model=UserResponse, summary="Update user profile")
async def update_user_endpoint(user_id: str, data: UserUpdate, db: AsyncSession = Depends(get_db)):
    """Update user profile including display name and locale preference."""
    user = await update_user(db, user_id, data)
    return user
