"""Seed initial data for development."""

import asyncio

from sqlalchemy import select

from src.domain.constants import PROFILE_DEFINITION_2024
from src.infrastructure.database import async_session_factory
from src.infrastructure.models import ProfileDefinition
from src.logging_config import get_logger

logger = get_logger(__name__)


async def seed_profile_definitions():
    async with async_session_factory() as session:
        existing = await session.execute(
            select(ProfileDefinition).where(ProfileDefinition.year == 2024)
        )
        if existing.scalar_one_or_none() is None:
            definition = ProfileDefinition(
                year=2024,
                schema_definition=PROFILE_DEFINITION_2024,
            )
            session.add(definition)
            await session.commit()
            logger.info("Seeded ProfileDefinition for 2024")
        else:
            logger.info("ProfileDefinition for 2024 already exists, skipping")


async def run_seed():
    await seed_profile_definitions()


if __name__ == "__main__":
    asyncio.run(run_seed())
