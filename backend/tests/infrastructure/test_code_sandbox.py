"""Tests for infrastructure/code_sandbox.py — CodeSandbox validation."""

from pathlib import Path

from src.infrastructure.code_sandbox import CodeSandbox, ValidationResult

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_golden_code(name: str) -> str:
    """Load a golden code fixture from tests/fixtures/generated_code/."""
    return (FIXTURES / "generated_code" / name).read_text()


class TestValidateCleanCode:
    """Tests that valid, safe code passes sandbox validation."""

    def test_valid_function_passes(self):
        code = _load_golden_code("calc_income_tax_valid.py")
        result = CodeSandbox.validate(code, expected_function_name="calc_income_tax")

        assert isinstance(result, ValidationResult)
        assert result.passed is True
        assert result.errors == []

    def test_simple_pure_function_passes(self):
        code = "def calc_basic_deduction(total_income):\n    if total_income <= 24_000_000:\n        return 480_000\n    return 0\n"
        result = CodeSandbox.validate(code, expected_function_name="calc_basic_deduction")

        assert result.passed is True
        assert result.errors == []

    def test_function_with_math_operations_passes(self):
        code = (
            "def calc_salary_income_deduction(gross_salary):\n"
            "    if gross_salary <= 1_625_000:\n"
            "        return 550_000\n"
            "    elif gross_salary <= 1_800_000:\n"
            "        return int(gross_salary * 0.4) - 100_000\n"
            "    else:\n"
            "        return int(gross_salary * 0.1) + 1_100_000\n"
        )
        result = CodeSandbox.validate(code, expected_function_name="calc_salary_income_deduction")

        assert result.passed is True

    def test_no_expected_function_name_still_validates(self):
        code = "def any_function():\n    return 42\n"
        result = CodeSandbox.validate(code)

        assert result.passed is True


class TestValidateRejectsUnsafeCode:
    """Tests that unsafe code patterns are rejected."""

    def test_rejects_import_os(self):
        code = "import os\n\ndef calc_tax(income):\n    return 0\n"
        result = CodeSandbox.validate(code, expected_function_name="calc_tax")

        assert result.passed is False
        assert any("Import statement found" in e for e in result.errors)

    def test_rejects_from_import(self):
        code = "from pathlib import Path\n\ndef calc_tax(income):\n    return 0\n"
        result = CodeSandbox.validate(code, expected_function_name="calc_tax")

        assert result.passed is False
        assert any("Import statement found" in e for e in result.errors)

    def test_rejects_open_file(self):
        code = "def calc_tax(income):\n    f = open('/etc/passwd')\n    return 0\n"
        result = CodeSandbox.validate(code, expected_function_name="calc_tax")

        assert result.passed is False
        # RestrictedPython blocks open() via safe_builtins
        assert len(result.errors) > 0

    def test_rejects_exec(self):
        code = "def calc_tax(income):\n    exec('print(1)')\n    return 0\n"
        result = CodeSandbox.validate(code, expected_function_name="calc_tax")

        assert result.passed is False

    def test_rejects_dunder_access(self):
        code = "def calc_tax(income):\n    return income.__class__.__bases__\n"
        result = CodeSandbox.validate(code, expected_function_name="calc_tax")

        assert result.passed is False

    def test_rejects_syntax_error(self):
        code = "def calc_tax(income\n    return 0\n"
        result = CodeSandbox.validate(code, expected_function_name="calc_tax")

        assert result.passed is False
        assert any("Syntax error" in e or "syntax" in e.lower() for e in result.errors)


class TestValidateFunctionNameCheck:
    """Tests for the expected function name validation."""

    def test_wrong_function_name_fails(self):
        code = "def wrong_name(income):\n    return 0\n"
        result = CodeSandbox.validate(code, expected_function_name="calc_income_tax")

        assert result.passed is False
        assert any("Expected function 'calc_income_tax' not found" in e for e in result.errors)

    def test_multiple_functions_one_matching_passes(self):
        code = (
            "def helper(x):\n    return x * 2\n\n"
            "def calc_income_tax(income):\n    return helper(income)\n"
        )
        result = CodeSandbox.validate(code, expected_function_name="calc_income_tax")

        assert result.passed is True


class TestValidateWarnings:
    """Tests that warnings are generated for non-critical issues."""

    def test_top_level_assignment_warns(self):
        code = "TAX_RATE = 0.1\n\ndef calc_tax(income):\n    return int(income * TAX_RATE)\n"
        result = CodeSandbox.validate(code, expected_function_name="calc_tax")

        assert result.passed is True
        assert any("Top-level variable assignment" in w for w in result.warnings)


class TestValidationResultStructure:
    """Tests for the ValidationResult dataclass."""

    def test_passed_result_has_empty_errors(self):
        code = "def calc_tax(income):\n    return 0\n"
        result = CodeSandbox.validate(code)

        assert result.passed is True
        assert result.errors == []
        assert isinstance(result.warnings, list)

    def test_failed_result_has_errors(self):
        code = "import sys\ndef calc_tax(income):\n    return 0\n"
        result = CodeSandbox.validate(code)

        assert result.passed is False
        assert len(result.errors) > 0
