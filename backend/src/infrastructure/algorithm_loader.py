"""Algorithm hot-loader.

Loads active algorithm code from the AlgorithmRegistry and
makes it callable at runtime.
"""
import types
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import AlgorithmStatus
from src.infrastructure.models import AlgorithmRegistry
from src.logging_config import get_logger

logger = get_logger(__name__)


class AlgorithmLoader:
    """Loads and caches active algorithms from the registry."""

    def __init__(self):
        self._cache: dict[str, Callable] = {}

    async def load_active_algorithms(self, db: AsyncSession) -> dict[str, Callable]:
        """Load all ACTIVE algorithms from the registry.

        Returns:
            Dict mapping function_name to callable function.
        """
        result = await db.execute(
            select(AlgorithmRegistry).where(AlgorithmRegistry.status == AlgorithmStatus.ACTIVE.value)
        )
        algorithms = result.scalars().all()

        loaded = {}
        for algo in algorithms:
            try:
                fn = self._compile_function(algo.function_name, algo.code_content)
                loaded[algo.function_name] = fn
                logger.info("Loaded algorithm '%s' v%s", algo.function_name, algo.version)
            except Exception as e:
                logger.error("Failed to compile algorithm '%s' v%s: %s", algo.function_name, algo.version, e)

        self._cache = loaded
        return loaded

    def get_function(self, function_name: str) -> Callable | None:
        """Get a loaded function by name from the cache."""
        return self._cache.get(function_name)

    def _compile_function(self, function_name: str, code_content: str) -> Callable:
        """Compile Python source code into a callable function.

        WARNING: This executes arbitrary code. Only use with admin-approved code
        from the AlgorithmRegistry.

        TODO: For defense-in-depth, restrict __builtins__ to a whitelist of safe
        functions (int, max, min, abs, round, range, len) in a future hardening pass.
        """
        module = types.ModuleType(f"taxpilot_algo_{function_name}")
        exec(code_content, module.__dict__)  # noqa: S102

        fn = getattr(module, function_name, None)
        if fn is None or not callable(fn):
            raise ValueError(f"Code for '{function_name}' does not define a callable with that name.")
        return fn
