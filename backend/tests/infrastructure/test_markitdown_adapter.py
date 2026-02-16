from unittest.mock import MagicMock

import pytest

from src.infrastructure.markitdown_adapter import MarkItDownAdapter


def test_is_supported_should_accept_pdf():
    adapter = MarkItDownAdapter()
    assert adapter.is_supported("salary_slip.pdf") is True


def test_is_supported_should_reject_txt():
    adapter = MarkItDownAdapter()
    assert adapter.is_supported("notes.txt") is False


def test_is_supported_should_accept_xlsx():
    adapter = MarkItDownAdapter()
    assert adapter.is_supported("transactions.xlsx") is True


def test_convert_should_return_markdown():
    mock_instance = MagicMock()
    mock_result = MagicMock()
    mock_result.text_content = "| Date | Amount |\n|---|---|\n| 2024-01 | 500000 |"
    mock_instance.convert.return_value = mock_result

    adapter = MarkItDownAdapter()
    adapter._converter = mock_instance

    result = adapter.convert_to_markdown("salary.pdf")
    assert "500000" in result


def test_convert_unsupported_should_raise_value_error():
    adapter = MarkItDownAdapter()
    with pytest.raises(ValueError, match="Unsupported file type"):
        adapter.convert_to_markdown("readme.txt")
