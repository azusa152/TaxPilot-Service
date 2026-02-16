import pytest

from src.infrastructure.algorithm_loader import AlgorithmLoader


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
