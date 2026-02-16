"""Tests for domain/prompts.py — prompt template rendering."""

from src.domain.prompts import (
    CODE_GENERATION_PROMPT,
    REGULATION_PARSE_PROMPT,
    REGULATION_PARSE_PROMPT_FIRST_SNAPSHOT,
    SCHEMA_GENERATION_PROMPT,
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


class TestCodeGenerationPrompt:
    """Tests for the code generation prompt template."""

    def test_renders_with_all_placeholders(self):
        result = CODE_GENERATION_PROMPT.format(
            change_type="THRESHOLD_UPDATE",
            affected_function="calc_basic_deduction",
            description="Basic deduction threshold increased",
            old_value="480,000 JPY",
            new_value="500,000 JPY",
            current_code="def calc_basic_deduction(income):\n    return 480_000",
            admin_hints="None",
        )

        assert "THRESHOLD_UPDATE" in result
        assert "calc_basic_deduction" in result
        assert "480,000 JPY" in result
        assert "500,000 JPY" in result

    def test_no_undefined_placeholders(self):
        result = CODE_GENERATION_PROMPT.format(
            change_type="RATE_CHANGE",
            affected_function="calc_tax",
            description="desc",
            old_value="old",
            new_value="new",
            current_code="code",
            admin_hints="None",
        )
        assert "{" not in result
        assert "}" not in result

    def test_contains_pure_function_requirement(self):
        result = CODE_GENERATION_PROMPT.format(
            change_type="t",
            affected_function="f",
            description="d",
            old_value="o",
            new_value="n",
            current_code="c",
            admin_hints="None",
        )
        assert "PURE Python function" in result
        assert "no imports" in result

    def test_contains_response_format_instructions(self):
        result = CODE_GENERATION_PROMPT.format(
            change_type="t",
            affected_function="f",
            description="d",
            old_value="o",
            new_value="n",
            current_code="c",
            admin_hints="None",
        )
        assert "CodeGenerationResult" in result

    def test_admin_hints_placeholder_rendered(self):
        result = CODE_GENERATION_PROMPT.format(
            change_type="t",
            affected_function="f",
            description="d",
            old_value="o",
            new_value="n",
            current_code="c",
            admin_hints="Use integer division for all calculations",
        )
        assert "Use integer division for all calculations" in result


class TestSchemaGenerationPrompt:
    """Tests for the schema generation prompt template."""

    def test_renders_with_all_placeholders(self):
        result = SCHEMA_GENERATION_PROMPT.format(
            changes_json='[{"change_type": "NEW_FIELD_REQUIRED"}]',
            current_fields='{"has_spouse": {"type": "bool"}}',
        )

        assert "NEW_FIELD_REQUIRED" in result
        assert "has_spouse" in result

    def test_all_placeholders_resolved(self):
        """format() should succeed without KeyError — all placeholders are defined."""
        result = SCHEMA_GENERATION_PROMPT.format(
            changes_json="CHANGES_MARKER",
            current_fields="FIELDS_MARKER",
        )
        assert "CHANGES_MARKER" in result
        assert "FIELDS_MARKER" in result
        # No unresolved placeholders remain (the prompt template has no
        # other {name} patterns besides changes_json and current_fields)
        assert "{changes_json}" not in result
        assert "{current_fields}" not in result

    def test_contains_response_format_instructions(self):
        result = SCHEMA_GENERATION_PROMPT.format(
            changes_json="[]",
            current_fields="{}",
        )
        assert "SchemaChangeProposal" in result

    def test_contains_field_definition_instructions(self):
        result = SCHEMA_GENERATION_PROMPT.format(
            changes_json="[]",
            current_fields="{}",
        )
        assert "snake_case" in result
        assert "Japanese description" in result
