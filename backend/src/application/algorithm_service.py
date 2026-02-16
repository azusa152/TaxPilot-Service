from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import AlgorithmStatus
from src.domain.exceptions import TaxPilotError
from src.infrastructure.models import AlgorithmRegistry
from src.logging_config import get_logger

logger = get_logger(__name__)


async def list_algorithms(db: AsyncSession) -> list[AlgorithmRegistry]:
    result = await db.execute(select(AlgorithmRegistry).order_by(AlgorithmRegistry.function_name))
    return list(result.scalars().all())


async def get_algorithm(db: AsyncSession, function_name: str) -> AlgorithmRegistry:
    result = await db.execute(
        select(AlgorithmRegistry).where(
            AlgorithmRegistry.function_name == function_name,
            AlgorithmRegistry.status == AlgorithmStatus.ACTIVE.value,
        )
    )
    algo = result.scalar_one_or_none()
    if algo is None:
        raise TaxPilotError(404, "ALGORITHM_NOT_FOUND", f"No active algorithm with function_name '{function_name}'.")
    return algo


async def register_algorithm(
    db: AsyncSession,
    function_name: str,
    version: str,
    code_content: str,
    source_law_hash: str | None = None,
) -> AlgorithmRegistry:
    algo = AlgorithmRegistry(
        function_name=function_name,
        version=version,
        code_content=code_content,
        status=AlgorithmStatus.DRAFT.value,
        source_law_hash=source_law_hash,
    )
    db.add(algo)
    await db.flush()
    logger.info("Registered algorithm '%s' v%s as DRAFT", function_name, version)
    return algo


async def activate_algorithm(db: AsyncSession, algorithm_id: int) -> AlgorithmRegistry:
    result = await db.execute(select(AlgorithmRegistry).where(AlgorithmRegistry.id == algorithm_id))
    algo = result.scalar_one_or_none()
    if algo is None:
        raise TaxPilotError(404, "ALGORITHM_NOT_FOUND", f"Algorithm with id {algorithm_id} not found.")

    # Archive previous active version of the same function
    await db.execute(
        update(AlgorithmRegistry)
        .where(
            AlgorithmRegistry.function_name == algo.function_name,
            AlgorithmRegistry.status == AlgorithmStatus.ACTIVE.value,
        )
        .values(status=AlgorithmStatus.ARCHIVED.value)
    )

    algo.status = AlgorithmStatus.ACTIVE.value
    await db.flush()
    logger.info("Activated algorithm '%s' v%s (id=%d)", algo.function_name, algo.version, algo.id)
    return algo
