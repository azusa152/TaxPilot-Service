from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.exceptions import TaxPilotError
from src.domain.schemas import UserCreate
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
