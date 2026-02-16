"""Tests for infrastructure/code_generator.py — CodeGenerator."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from src.domain.enums import CrawlerRunTrigger, LawChangeType
from src.domain.exceptions import LlmCallError
from src.domain.schemas import CodeGenerationResult, LawChange
from src.infrastructure.code_generator import CodeGenerator
from src.infrastructure.models import AlgorithmRegistry, EvolutionRun, GenerationAttempt

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_fixture(name: str) -> dict:
    """Load a JSON fixture from tests/fixtures/llm_responses/."""
    return json.loads((FIXTURES / "llm_responses" / name).read_text())


def _make_law_change() -> LawChange:
    """Create a sample LawChange for testing."""
    return LawChange(
        change_type=LawChangeType.NEW_DEDUCTION,
        affected_function="calc_income_tax",
        old_value="N/A",
        new_value="30,000 JPY credit per person",
        description="2024 Fixed Tax Cut: 30,000 JPY per eligible person",
        confidence_score=0.95,
    )


def _make_llm_service(response_json: dict) -> AsyncMock:
    """Create a mocked LlmService that returns a CodeGenerationResult."""
    llm = AsyncMock()
    llm.generate_structured = AsyncMock(
        return_value=CodeGenerationResult.model_validate(response_json)
    )
    return llm


CURRENT_CODE = '''def calc_income_tax(taxable_income):
    """Calculate income tax based on taxable income."""
    if taxable_income <= 1_950_000:
        tax = int(taxable_income * 0.05)
    elif taxable_income <= 3_300_000:
        tax = int(taxable_income * 0.10) - 97_500
    else:
        tax = int(taxable_income * 0.20) - 427_500
    return tax
'''


@pytest.fixture()
async def evolution_run(db_session):
    """Create an EvolutionRun for FK references in generation tests."""
    run = EvolutionRun(trigger=CrawlerRunTrigger.MANUAL)
    db_session.add(run)
    await db_session.flush()
    return run


class TestCodeGeneratorGenerate:
    """Tests for CodeGenerator.generate() method."""

    async def test_returns_code_generation_result(self, db_session, evolution_run):
        fixture = _load_fixture("code_generation_valid.json")
        llm = _make_llm_service(fixture)

        generator = CodeGenerator(llm_service=llm, db=db_session)
        result, passed = await generator.generate(
            law_change=_make_law_change(),
            current_code=CURRENT_CODE,
            evolution_run_id=evolution_run.id,
        )

        assert isinstance(result, CodeGenerationResult)
        assert result.function_name == "calc_income_tax"
        assert result.version == "2024.1"
        assert "calc_income_tax" in result.code_content

    async def test_valid_code_passes_sandbox(self, db_session, evolution_run):
        fixture = _load_fixture("code_generation_valid.json")
        llm = _make_llm_service(fixture)

        generator = CodeGenerator(llm_service=llm, db=db_session)
        _, passed = await generator.generate(
            law_change=_make_law_change(),
            current_code=CURRENT_CODE,
            evolution_run_id=evolution_run.id,
        )

        assert passed is True

    async def test_stores_generation_attempt(self, db_session, evolution_run):
        fixture = _load_fixture("code_generation_valid.json")
        llm = _make_llm_service(fixture)

        generator = CodeGenerator(llm_service=llm, db=db_session)
        await generator.generate(
            law_change=_make_law_change(),
            current_code=CURRENT_CODE,
            evolution_run_id=evolution_run.id,
        )

        attempts = (await db_session.execute(select(GenerationAttempt))).scalars().all()
        assert len(attempts) == 1
        assert attempts[0].attempt_number == 1
        assert attempts[0].validation_passed is True
        assert attempts[0].validation_errors is None

    async def test_stores_draft_algorithm_on_success(self, db_session, evolution_run):
        fixture = _load_fixture("code_generation_valid.json")
        llm = _make_llm_service(fixture)

        generator = CodeGenerator(llm_service=llm, db=db_session)
        await generator.generate(
            law_change=_make_law_change(),
            current_code=CURRENT_CODE,
            evolution_run_id=evolution_run.id,
        )

        drafts = (await db_session.execute(select(AlgorithmRegistry))).scalars().all()
        assert len(drafts) == 1
        assert drafts[0].function_name == "calc_income_tax"
        assert drafts[0].status == "DRAFT"
        assert drafts[0].version == "2024.1"

    async def test_unsafe_code_fails_validation(self, db_session, evolution_run):
        fixture = _load_fixture("code_generation_unsafe.json")
        llm = _make_llm_service(fixture)

        generator = CodeGenerator(llm_service=llm, db=db_session)
        _, passed = await generator.generate(
            law_change=_make_law_change(),
            current_code=CURRENT_CODE,
            evolution_run_id=evolution_run.id,
        )

        assert passed is False

    async def test_unsafe_code_no_draft_stored(self, db_session, evolution_run):
        fixture = _load_fixture("code_generation_unsafe.json")
        llm = _make_llm_service(fixture)

        generator = CodeGenerator(llm_service=llm, db=db_session)
        await generator.generate(
            law_change=_make_law_change(),
            current_code=CURRENT_CODE,
            evolution_run_id=evolution_run.id,
        )

        drafts = (await db_session.execute(select(AlgorithmRegistry))).scalars().all()
        assert len(drafts) == 0

    async def test_unsafe_code_stores_attempt_with_errors(self, db_session, evolution_run):
        fixture = _load_fixture("code_generation_unsafe.json")
        llm = _make_llm_service(fixture)

        generator = CodeGenerator(llm_service=llm, db=db_session)
        await generator.generate(
            law_change=_make_law_change(),
            current_code=CURRENT_CODE,
            evolution_run_id=evolution_run.id,
        )

        attempts = (await db_session.execute(select(GenerationAttempt))).scalars().all()
        assert len(attempts) == 1
        assert attempts[0].validation_passed is False
        assert attempts[0].validation_errors is not None
        assert "errors" in attempts[0].validation_errors

    async def test_passes_caller_and_evolution_run_id(self, db_session, evolution_run):
        fixture = _load_fixture("code_generation_valid.json")
        llm = _make_llm_service(fixture)

        generator = CodeGenerator(llm_service=llm, db=db_session)
        await generator.generate(
            law_change=_make_law_change(),
            current_code=CURRENT_CODE,
            evolution_run_id=evolution_run.id,
        )

        call_args = llm.generate_structured.call_args
        assert call_args.kwargs["caller"] == "code_generator"
        assert call_args.kwargs["evolution_run_id"] == evolution_run.id
        assert call_args.kwargs["response_format"] is CodeGenerationResult

    async def test_admin_hints_in_prompt_and_attempt(self, db_session, evolution_run):
        fixture = _load_fixture("code_generation_valid.json")
        llm = _make_llm_service(fixture)

        generator = CodeGenerator(llm_service=llm, db=db_session)
        await generator.generate(
            law_change=_make_law_change(),
            current_code=CURRENT_CODE,
            evolution_run_id=evolution_run.id,
            attempt_number=2,
            admin_hints="Use integer division only",
        )

        call_args = llm.generate_structured.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "Use integer division only" in prompt

        attempts = (await db_session.execute(select(GenerationAttempt))).scalars().all()
        assert attempts[0].attempt_number == 2
        assert attempts[0].admin_hints == "Use integer division only"

    async def test_prompt_contains_law_change_details(self, db_session, evolution_run):
        fixture = _load_fixture("code_generation_valid.json")
        llm = _make_llm_service(fixture)

        generator = CodeGenerator(llm_service=llm, db=db_session)
        await generator.generate(
            law_change=_make_law_change(),
            current_code=CURRENT_CODE,
            evolution_run_id=evolution_run.id,
        )

        call_args = llm.generate_structured.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "NEW_DEDUCTION" in prompt
        assert "calc_income_tax" in prompt
        assert "2024 Fixed Tax Cut" in prompt


class TestCodeGeneratorErrorHandling:
    """Tests for error cases in CodeGenerator."""

    async def test_llm_failure_stores_failed_attempt(self, db_session, evolution_run):
        llm = AsyncMock()
        llm.generate_structured = AsyncMock(
            side_effect=LlmCallError("LLM provider returned 503")
        )

        generator = CodeGenerator(llm_service=llm, db=db_session)
        with pytest.raises(LlmCallError, match="503"):
            await generator.generate(
                law_change=_make_law_change(),
                current_code=CURRENT_CODE,
                evolution_run_id=evolution_run.id,
            )

        # Failed attempt should still be stored for audit trail
        attempts = (await db_session.execute(select(GenerationAttempt))).scalars().all()
        assert len(attempts) == 1
        assert attempts[0].validation_passed is False
        assert attempts[0].generated_code == ""
        assert "503" in str(attempts[0].validation_errors)

    async def test_llm_failure_no_draft_stored(self, db_session, evolution_run):
        llm = AsyncMock()
        llm.generate_structured = AsyncMock(
            side_effect=LlmCallError("Network timeout")
        )

        generator = CodeGenerator(llm_service=llm, db=db_session)
        with pytest.raises(LlmCallError):
            await generator.generate(
                law_change=_make_law_change(),
                current_code=CURRENT_CODE,
                evolution_run_id=evolution_run.id,
            )

        # No draft should be stored on LLM failure
        drafts = (await db_session.execute(select(AlgorithmRegistry))).scalars().all()
        assert len(drafts) == 0
