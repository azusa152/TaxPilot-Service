import pytest
from sqlalchemy import select

from src.domain.enums import AlgorithmStatus
from src.infrastructure.algorithm_loader import AlgorithmLoader
from src.infrastructure.models import AlgorithmRegistry


def test_compile_function_should_return_callable():
    loader = AlgorithmLoader()
    code = "def calc_test(x):\n    return x * 2\n"
    fn = loader._compile_function("calc_test", code)
    assert fn(5) == 10


def test_compile_function_missing_name_should_raise():
    loader = AlgorithmLoader()
    code = "def wrong_name(x):\n    return x\n"
    with pytest.raises(ValueError, match="calc_test"):
        loader._compile_function("calc_test", code)


def test_get_function_returns_none_when_not_loaded():
    loader = AlgorithmLoader()
    assert loader.get_function("nonexistent") is None


class TestLoadActiveAlgorithms:
    """Tests for loading algorithms from the registry."""

    async def test_loads_active_algorithm_from_registry(self, db_session):
        """Should load and execute an ACTIVE algorithm from the registry."""
        code = "def calc_test(x):\n    return x * 3\n"
        algo = AlgorithmRegistry(
            function_name="calc_test",
            version="2024.1",
            code_content=code,
            status=AlgorithmStatus.ACTIVE,
        )
        db_session.add(algo)
        await db_session.flush()

        loader = AlgorithmLoader()
        loaded = await loader.load_active_algorithms(db_session)

        assert "calc_test" in loaded
        assert loaded["calc_test"](10) == 30

    async def test_skips_draft_algorithms(self, db_session):
        """Should not load DRAFT algorithms."""
        code = "def calc_draft(x):\n    return x\n"
        algo = AlgorithmRegistry(
            function_name="calc_draft",
            version="2024.1",
            code_content=code,
            status=AlgorithmStatus.DRAFT,
        )
        db_session.add(algo)
        await db_session.flush()

        loader = AlgorithmLoader()
        loaded = await loader.load_active_algorithms(db_session)

        assert "calc_draft" not in loaded

    async def test_returns_empty_when_registry_is_empty(self, db_session):
        """Empty registry should return empty dict."""
        loader = AlgorithmLoader()
        loaded = await loader.load_active_algorithms(db_session)
        assert loaded == {}

    async def test_get_function_returns_loaded_function(self, db_session):
        """get_function should return the loaded function after load_active_algorithms."""
        code = "def calc_cached(x):\n    return x + 1\n"
        algo = AlgorithmRegistry(
            function_name="calc_cached",
            version="1.0",
            code_content=code,
            status=AlgorithmStatus.ACTIVE,
        )
        db_session.add(algo)
        await db_session.flush()

        loader = AlgorithmLoader()
        await loader.load_active_algorithms(db_session)

        fn = loader.get_function("calc_cached")
        assert fn is not None
        assert fn(5) == 6
