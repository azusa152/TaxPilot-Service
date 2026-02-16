"""Tests for infrastructure/schema_generator.py — SchemaGenerator."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from src.domain.enums import CrawlerRunTrigger, LawChangeType
from src.domain.exceptions import LlmCallError
from src.domain.schemas import LawChange, SchemaChangeProposal
from src.infrastructure.models import EvolutionRun, SchemaChangeProposalRecord
from src.infrastructure.schema_generator import SchemaGenerator

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_fixture(name: str) -> dict:
    """Load a JSON fixture from tests/fixtures/llm_responses/."""
    return json.loads((FIXTURES / "llm_responses" / name).read_text())


def _make_law_changes() -> list[LawChange]:
    """Create sample LawChange objects for testing."""
    return [
        LawChange(
            change_type=LawChangeType.NEW_DEDUCTION,
            affected_function="calc_income_tax",
            old_value="N/A",
            new_value="30,000 JPY credit per person",
            description="2024 Fixed Tax Cut: 30,000 JPY per eligible person",
            confidence_score=0.95,
        ),
        LawChange(
            change_type=LawChangeType.NEW_FIELD_REQUIRED,
            affected_function="calc_income_tax",
            old_value="N/A",
            new_value="fixed_tax_cut_eligible_count: int",
            description="New field: number of persons eligible for the fixed tax cut",
            confidence_score=0.90,
        ),
    ]


CURRENT_FIELDS = {
    "has_spouse": {"type": "bool", "required": False, "default": False},
    "dependents_count": {"type": "int", "required": False, "default": 0},
    "social_insurance_premium": {"type": "int", "required": False, "default": 0},
}


def _make_llm_service(response_json: dict) -> AsyncMock:
    """Create a mocked LlmService that returns a SchemaChangeProposal."""
    llm = AsyncMock()
    llm.generate_structured = AsyncMock(
        return_value=SchemaChangeProposal.model_validate(response_json)
    )
    return llm


@pytest.fixture()
async def evolution_run(db_session):
    """Create an EvolutionRun for FK references in schema generator tests."""
    run = EvolutionRun(trigger=CrawlerRunTrigger.MANUAL)
    db_session.add(run)
    await db_session.flush()
    return run


class TestSchemaGeneratorGenerate:
    """Tests for SchemaGenerator.generate() method."""

    async def test_returns_schema_change_proposal(self, db_session, evolution_run):
        fixture = _load_fixture("schema_change_proposal.json")
        llm = _make_llm_service(fixture)

        generator = SchemaGenerator(llm_service=llm, db=db_session)
        result = await generator.generate(
            changes=_make_law_changes(),
            current_fields=CURRENT_FIELDS,
            evolution_run_id=evolution_run.id,
        )

        assert isinstance(result, SchemaChangeProposal)
        assert result.year == 2024
        assert len(result.new_fields) == 1
        assert result.new_fields[0].name == "fixed_tax_cut_eligible_count"

    async def test_new_field_has_valid_definition(self, db_session, evolution_run):
        fixture = _load_fixture("schema_change_proposal.json")
        llm = _make_llm_service(fixture)

        generator = SchemaGenerator(llm_service=llm, db=db_session)
        result = await generator.generate(
            changes=_make_law_changes(),
            current_fields=CURRENT_FIELDS,
            evolution_run_id=evolution_run.id,
        )

        field = result.new_fields[0]
        assert field.type == "int"
        assert field.required is False
        assert field.default_value == "0"
        assert field.description  # non-empty
        assert field.description_ja  # non-empty

    async def test_stores_proposal_record(self, db_session, evolution_run):
        fixture = _load_fixture("schema_change_proposal.json")
        llm = _make_llm_service(fixture)

        generator = SchemaGenerator(llm_service=llm, db=db_session)
        await generator.generate(
            changes=_make_law_changes(),
            current_fields=CURRENT_FIELDS,
            evolution_run_id=evolution_run.id,
        )

        records = (
            await db_session.execute(select(SchemaChangeProposalRecord))
        ).scalars().all()
        assert len(records) == 1
        assert records[0].year == 2024
        assert records[0].status == "PENDING"
        assert records[0].evolution_run_id == evolution_run.id
        assert "new_fields" in records[0].proposal_data

    async def test_passes_caller_and_evolution_run_id(self, db_session, evolution_run):
        fixture = _load_fixture("schema_change_proposal.json")
        llm = _make_llm_service(fixture)

        generator = SchemaGenerator(llm_service=llm, db=db_session)
        await generator.generate(
            changes=_make_law_changes(),
            current_fields=CURRENT_FIELDS,
            evolution_run_id=evolution_run.id,
        )

        call_args = llm.generate_structured.call_args
        assert call_args.kwargs["caller"] == "schema_generator"
        assert call_args.kwargs["evolution_run_id"] == evolution_run.id
        assert call_args.kwargs["response_format"] is SchemaChangeProposal

    async def test_prompt_contains_changes_and_fields(self, db_session, evolution_run):
        fixture = _load_fixture("schema_change_proposal.json")
        llm = _make_llm_service(fixture)

        generator = SchemaGenerator(llm_service=llm, db=db_session)
        await generator.generate(
            changes=_make_law_changes(),
            current_fields=CURRENT_FIELDS,
            evolution_run_id=evolution_run.id,
        )

        call_args = llm.generate_structured.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "NEW_DEDUCTION" in prompt
        assert "NEW_FIELD_REQUIRED" in prompt
        assert "has_spouse" in prompt

    async def test_removed_fields_empty_by_default(self, db_session, evolution_run):
        fixture = _load_fixture("schema_change_proposal.json")
        llm = _make_llm_service(fixture)

        generator = SchemaGenerator(llm_service=llm, db=db_session)
        result = await generator.generate(
            changes=_make_law_changes(),
            current_fields=CURRENT_FIELDS,
            evolution_run_id=evolution_run.id,
        )

        assert result.removed_fields == []
        assert result.change_rationale  # non-empty


class TestSchemaGeneratorNoNewFields:
    """Tests for threshold-only changes that need no new fields."""

    async def test_threshold_only_returns_empty_new_fields(self, db_session, evolution_run):
        fixture = _load_fixture("schema_no_new_fields.json")
        llm = _make_llm_service(fixture)

        threshold_only = [
            LawChange(
                change_type=LawChangeType.THRESHOLD_UPDATE,
                affected_function="calc_basic_deduction",
                old_value="480,000 JPY",
                new_value="500,000 JPY",
                description="Basic deduction threshold increased",
                confidence_score=0.90,
            ),
        ]

        generator = SchemaGenerator(llm_service=llm, db=db_session)
        result = await generator.generate(
            changes=threshold_only,
            current_fields=CURRENT_FIELDS,
            evolution_run_id=evolution_run.id,
        )

        assert result.new_fields == []
        assert result.removed_fields == []
        assert result.change_rationale  # non-empty

    async def test_no_new_fields_still_stores_proposal(self, db_session, evolution_run):
        fixture = _load_fixture("schema_no_new_fields.json")
        llm = _make_llm_service(fixture)

        generator = SchemaGenerator(llm_service=llm, db=db_session)
        await generator.generate(
            changes=[
                LawChange(
                    change_type=LawChangeType.RATE_CHANGE,
                    affected_function="calc_income_tax",
                    old_value="5% bracket up to 1,950,000",
                    new_value="5% bracket up to 2,000,000",
                    description="First tax bracket ceiling raised",
                    confidence_score=0.85,
                ),
            ],
            current_fields=CURRENT_FIELDS,
            evolution_run_id=evolution_run.id,
        )

        records = (
            await db_session.execute(select(SchemaChangeProposalRecord))
        ).scalars().all()
        assert len(records) == 1
        assert records[0].proposal_data["new_fields"] == []


class TestSchemaGeneratorErrorHandling:
    """Tests for error cases in SchemaGenerator."""

    async def test_llm_failure_raises_and_stores_nothing(self, db_session, evolution_run):
        llm = AsyncMock()
        llm.generate_structured = AsyncMock(
            side_effect=LlmCallError("LLM provider returned 503")
        )

        generator = SchemaGenerator(llm_service=llm, db=db_session)
        with pytest.raises(LlmCallError, match="503"):
            await generator.generate(
                changes=_make_law_changes(),
                current_fields=CURRENT_FIELDS,
                evolution_run_id=evolution_run.id,
            )

        # No proposal should be stored on LLM failure
        records = (
            await db_session.execute(select(SchemaChangeProposalRecord))
        ).scalars().all()
        assert len(records) == 0
