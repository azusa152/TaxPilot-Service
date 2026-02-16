"""Tests for domain/prompts.py — prompt template rendering."""

from src.domain.prompts import (
    REGULATION_PARSE_PROMPT,
    REGULATION_PARSE_PROMPT_FIRST_SNAPSHOT,
)


class TestRegulationParsePrompt:
    """Tests for the regulation comparison prompt template."""

    def test_renders_with_all_placeholders(self):
        result = REGULATION_PARSE_PROMPT.format(
            new_content="# New tax rates page",
            old_content="# Old tax rates page",
            known_functions="- calc_income_tax\n- calc_basic_deduction",
        )

        assert "# New tax rates page" in result
        assert "# Old tax rates page" in result
        assert "- calc_income_tax" in result
        assert "- calc_basic_deduction" in result

    def test_no_undefined_placeholders(self):
        """Rendered prompt should not contain unresolved {placeholder} markers."""
        result = REGULATION_PARSE_PROMPT.format(
            new_content="new content",
            old_content="old content",
            known_functions="- calc_income_tax",
        )
        # Should not contain any remaining {…} placeholders
        assert "{" not in result
        assert "}" not in result

    def test_contains_response_format_instructions(self):
        result = REGULATION_PARSE_PROMPT.format(
            new_content="content",
            old_content="old",
            known_functions="- func",
        )
        assert "RegulationAnalysis" in result

    def test_contains_change_type_instructions(self):
        result = REGULATION_PARSE_PROMPT.format(
            new_content="content",
            old_content="old",
            known_functions="- func",
        )
        assert "NEW_FIELD_REQUIRED" in result

    def test_known_functions_placeholder_rendered(self):
        """The {known_functions} placeholder should inject the supplied list."""
        unique_fn = "- calc_custom_test_function_xyz"
        result = REGULATION_PARSE_PROMPT.format(
            new_content="content",
            old_content="old",
            known_functions=unique_fn,
        )
        # This value only appears if the placeholder was actually rendered
        assert "calc_custom_test_function_xyz" in result


class TestRegulationParsePromptFirstSnapshot:
    """Tests for the first-snapshot (baseline) prompt template."""

    def test_renders_with_all_placeholders(self):
        result = REGULATION_PARSE_PROMPT_FIRST_SNAPSHOT.format(
            content="# Income tax rates page",
            known_functions="- calc_income_tax",
        )
        assert "# Income tax rates page" in result
        assert "calc_income_tax" in result

    def test_no_undefined_placeholders(self):
        result = REGULATION_PARSE_PROMPT_FIRST_SNAPSHOT.format(
            content="content",
            known_functions="- func",
        )
        assert "{" not in result
        assert "}" not in result

    def test_contains_baseline_instructions(self):
        result = REGULATION_PARSE_PROMPT_FIRST_SNAPSHOT.format(
            content="content",
            known_functions="- func",
        )
        assert "BASELINE" in result
        assert "THRESHOLD_UPDATE" in result

    def test_contains_response_format_instructions(self):
        result = REGULATION_PARSE_PROMPT_FIRST_SNAPSHOT.format(
            content="content",
            known_functions="- func",
        )
        assert "RegulationAnalysis" in result

    def test_known_functions_placeholder_rendered(self):
        """The {known_functions} placeholder should inject the supplied list."""
        unique_fn = "- calc_custom_baseline_xyz"
        result = REGULATION_PARSE_PROMPT_FIRST_SNAPSHOT.format(
            content="content",
            known_functions=unique_fn,
        )
        assert "calc_custom_baseline_xyz" in result
