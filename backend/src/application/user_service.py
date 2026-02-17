from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.constants import SUPPORTED_LOCALES
from src.domain.exceptions import TaxPilotError
from src.domain.schemas import UserCreate, UserUpdate
from src.infrastructure.models import User


async def create_user(db: AsyncSession, data: UserCreate) -> User:
    user = User(display_name=data.display_name)
    db.add(user)
    await db.flush()
    return user


async def get_user(db: AsyncSession, user_id: str) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise TaxPilotError(404, "USER_NOT_FOUND", f"User '{user_id}' not found.")
    return user


async def update_user(db: AsyncSession, user_id: str, data: UserUpdate) -> User:
    """Update user profile including locale preference.
    
    Args:
        db: Async database session.
        user_id: UUID of the user to update.
        data: UserUpdate data with optional display_name and locale_preference.
    
    Returns:
        Updated User instance.
    
    Raises:
        TaxPilotError: If user not found or locale_preference is invalid.
    """
    user = await get_user(db, user_id)
    
    # Validate locale_preference if provided
    if data.locale_preference is not None and data.locale_preference not in SUPPORTED_LOCALES:
        raise TaxPilotError(
            400,
            "INVALID_LOCALE",
            f"Invalid locale '{data.locale_preference}'. Supported locales: {', '.join(SUPPORTED_LOCALES)}",
        )
    
    # Apply updates (only update fields that are not None)
    if data.display_name is not None:
        user.display_name = data.display_name
    if data.locale_preference is not None:
        user.locale_preference = data.locale_preference
    
    await db.flush()
    return user
