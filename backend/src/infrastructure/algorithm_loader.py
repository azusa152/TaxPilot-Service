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

# Safe builtins whitelist for algorithm execution (defense-in-depth).
# Admin-approved algorithms are validated by CodeSandbox, but this provides
# an additional runtime safety layer. Only math and basic operations are allowed.
_SAFE_BUILTINS = {
    "int": int,
    "float": float,
    "max": max,
    "min": min,
    "abs": abs,
    "round": round,
    "range": range,
    "len": len,
    "sum": sum,
    "bool": bool,
    "str": str,
    "True": True,
    "False": False,
    "None": None,
}


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
            select(AlgorithmRegistry).where(AlgorithmRegistry.status == AlgorithmStatus.ACTIVE)
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

        Uses a restricted builtins whitelist for defense-in-depth. Admin-approved
        algorithms are validated by CodeSandbox before activation, but this provides
        an additional runtime safety layer.
        """
        module = types.ModuleType(f"taxpilot_algo_{function_name}")
        restricted_globals = {"__builtins__": _SAFE_BUILTINS}
        # SECURITY NOTE: This exec() is used with a restricted builtins whitelist.
        # The code has already been validated by CodeSandbox and approved by an admin.
        # This restriction provides defense-in-depth by blocking dangerous operations
        # at runtime (e.g., file access, network calls, module imports).
        exec(code_content, restricted_globals)  # noqa: S102

        fn = restricted_globals.get(function_name)
        if fn is None or not callable(fn):
            raise ValueError(f"Code for '{function_name}' does not define a callable with that name.")
        return fn
