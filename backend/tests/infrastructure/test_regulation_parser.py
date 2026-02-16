"""Tests for infrastructure/regulation_parser.py — RegulationParser."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from src.domain.enums import LawChangeType, SnapshotStatus
from src.domain.exceptions import NotFoundError
from src.domain.schemas import RegulationAnalysis
from src.infrastructure.models import NtaPageSnapshot, NtaTargetPage
from src.infrastructure.regulation_parser import KNOWN_FUNCTIONS, RegulationParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_fixture(name: str) -> dict:
    """Load a JSON fixture from tests/fixtures/llm_responses/."""
    return json.loads((FIXTURES / "llm_responses" / name).read_text())


def _load_markdown(name: str) -> str:
    """Load a markdown fixture from tests/fixtures/nta_markdown/."""
    return (FIXTURES / "nta_markdown" / name).read_text()


def _make_llm_service(response_json: dict) -> AsyncMock:
    """Create a mocked LlmService that returns a RegulationAnalysis."""
    llm = AsyncMock()
    llm.generate_structured = AsyncMock(
        return_value=RegulationAnalysis.model_validate(response_json)
    )
    return llm


@pytest.fixture()
async def db_with_snapshot(db_session):
    """DB with a target page and one SUCCESS snapshot (first snapshot — no previous)."""
    page = NtaTargetPage(
        name="income_tax_rates",
        url="https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2260.htm",
        description="Income tax rate table",
        is_active=True,
    )
    db_session.add(page)
    await db_session.flush()

    snapshot = NtaPageSnapshot(
        target_page_id=page.id,
        content_hash="hash_v1",
        fit_markdown=_load_markdown("income_tax_rates_v1.md"),
        status=SnapshotStatus.SUCCESS,
    )
    db_session.add(snapshot)
    await db_session.flush()

    return db_session, snapshot


@pytest.fixture()
async def db_with_two_snapshots(db_session):
    """DB with a target page and two SUCCESS snapshots (for change comparison)."""
    page = NtaTargetPage(
        name="income_tax_rates",
        url="https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2260.htm",
        description="Income tax rate table",
        is_active=True,
    )
    db_session.add(page)
    await db_session.flush()

    snap1 = NtaPageSnapshot(
        target_page_id=page.id,
        content_hash="hash_v1",
        fit_markdown=_load_markdown("income_tax_rates_v1.md"),
        status=SnapshotStatus.SUCCESS,
    )
    db_session.add(snap1)
    await db_session.flush()

    snap2 = NtaPageSnapshot(
        target_page_id=page.id,
        content_hash="hash_v2",
        fit_markdown=_load_markdown("income_tax_rates_v2.md"),
        status=SnapshotStatus.SUCCESS,
    )
    db_session.add(snap2)
    await db_session.flush()

    return db_session, snap1, snap2


class TestParseFirstSnapshot:
    """Tests for parsing the first snapshot (baseline extraction)."""

    async def test_returns_validated_regulation_analysis(self, db_with_snapshot):
        db, snapshot = db_with_snapshot
        fixture = _load_fixture("regulation_baseline.json")
        llm = _make_llm_service(fixture)

        parser = RegulationParser(llm_service=llm, db=db)
        result = await parser.parse(snapshot.id)

        assert isinstance(result, RegulationAnalysis)
        assert len(result.changes) == 2
        assert result.tax_year == 2024
        assert result.no_changes_detected is False

    async def test_uses_first_snapshot_prompt(self, db_with_snapshot):
        """When there's no previous snapshot, the first-snapshot prompt is used."""
        db, snapshot = db_with_snapshot
        fixture = _load_fixture("regulation_baseline.json")
        llm = _make_llm_service(fixture)

        parser = RegulationParser(llm_service=llm, db=db)
        await parser.parse(snapshot.id)

        # Verify the prompt does NOT contain "Previous page content"
        call_args = llm.generate_structured.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "BASELINE" in prompt
        assert "Previous page content" not in prompt

    async def test_first_snapshot_prompt_includes_known_functions(self, db_with_snapshot):
        """First-snapshot prompt should include KNOWN_FUNCTIONS for consistent mapping."""
        db, snapshot = db_with_snapshot
        fixture = _load_fixture("regulation_baseline.json")
        llm = _make_llm_service(fixture)

        parser = RegulationParser(llm_service=llm, db=db)
        await parser.parse(snapshot.id)

        call_args = llm.generate_structured.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        for fn in KNOWN_FUNCTIONS:
            assert fn in prompt, f"{fn} missing from first-snapshot prompt"

    async def test_passes_caller_and_evolution_run_id(self, db_with_snapshot):
        db, snapshot = db_with_snapshot
        fixture = _load_fixture("regulation_baseline.json")
        llm = _make_llm_service(fixture)

        parser = RegulationParser(llm_service=llm, db=db)
        await parser.parse(snapshot.id, evolution_run_id=42)

        call_args = llm.generate_structured.call_args
        assert call_args.kwargs["caller"] == "regulation_parser"
        assert call_args.kwargs["evolution_run_id"] == 42
        assert call_args.kwargs["response_format"] is RegulationAnalysis


class TestParseWithPreviousSnapshot:
    """Tests for parsing with a previous snapshot (change detection)."""

    async def test_detects_changes_between_snapshots(self, db_with_two_snapshots):
        db, snap1, snap2 = db_with_two_snapshots
        fixture = _load_fixture("regulation_change_detected.json")
        llm = _make_llm_service(fixture)

        parser = RegulationParser(llm_service=llm, db=db)
        result = await parser.parse(snap2.id)

        assert len(result.changes) == 2
        assert result.changes[0].change_type == LawChangeType.NEW_DEDUCTION
        assert result.changes[0].affected_function == "calc_income_tax"
        assert result.changes[0].confidence_score == 0.95
        assert result.changes[1].change_type == LawChangeType.NEW_FIELD_REQUIRED

    async def test_uses_comparison_prompt(self, db_with_two_snapshots):
        """When a previous snapshot exists, the comparison prompt is used."""
        db, snap1, snap2 = db_with_two_snapshots
        fixture = _load_fixture("regulation_change_detected.json")
        llm = _make_llm_service(fixture)

        parser = RegulationParser(llm_service=llm, db=db)
        await parser.parse(snap2.id)

        call_args = llm.generate_structured.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "Previous page content" in prompt
        assert "Current page content" in prompt

    async def test_no_changes_detected_flag(self, db_with_two_snapshots):
        """Parser correctly propagates no_changes_detected=true."""
        db, snap1, snap2 = db_with_two_snapshots
        fixture = _load_fixture("regulation_no_changes.json")
        llm = _make_llm_service(fixture)

        parser = RegulationParser(llm_service=llm, db=db)
        result = await parser.parse(snap2.id)

        assert result.no_changes_detected is True
        assert result.changes == []


class TestParseErrorHandling:
    """Tests for error cases in RegulationParser.parse()."""

    async def test_snapshot_not_found_raises_not_found_error(self, db_session):
        llm = AsyncMock()
        parser = RegulationParser(llm_service=llm, db=db_session)

        with pytest.raises(NotFoundError, match="Snapshot 9999 not found"):
            await parser.parse(9999)

    async def test_snapshot_without_fit_markdown_raises(self, db_session):
        page = NtaTargetPage(
            name="test_page",
            url="https://example.com",
            is_active=True,
        )
        db_session.add(page)
        await db_session.flush()

        snapshot = NtaPageSnapshot(
            target_page_id=page.id,
            content_hash="empty",
            fit_markdown=None,
            status=SnapshotStatus.FAILED,
            error_message="crawl failed",
        )
        db_session.add(snapshot)
        await db_session.flush()

        llm = AsyncMock()
        parser = RegulationParser(llm_service=llm, db=db_session)

        with pytest.raises(NotFoundError, match="has no fit_markdown"):
            await parser.parse(snapshot.id)

    async def test_skips_failed_previous_snapshot(self, db_session):
        """Previous FAILED snapshot should be skipped; falls back to first-snapshot mode."""
        page = NtaTargetPage(
            name="test_page",
            url="https://example.com",
            is_active=True,
        )
        db_session.add(page)
        await db_session.flush()

        # First snapshot: FAILED (no fit_markdown)
        failed_snap = NtaPageSnapshot(
            target_page_id=page.id,
            content_hash="",
            fit_markdown=None,
            status=SnapshotStatus.FAILED,
        )
        db_session.add(failed_snap)
        await db_session.flush()

        # Second snapshot: SUCCESS
        good_snap = NtaPageSnapshot(
            target_page_id=page.id,
            content_hash="hash_good",
            fit_markdown="# Good content",
            status=SnapshotStatus.SUCCESS,
        )
        db_session.add(good_snap)
        await db_session.flush()

        fixture = _load_fixture("regulation_baseline.json")
        llm = _make_llm_service(fixture)

        parser = RegulationParser(llm_service=llm, db=db_session)
        await parser.parse(good_snap.id)

        # Should use first-snapshot prompt since previous was FAILED
        call_args = llm.generate_structured.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "BASELINE" in prompt


class TestLawChangeValidation:
    """Tests for Pydantic validation of LawChange fields."""

    def test_change_type_uses_enum(self):
        fixture = _load_fixture("regulation_change_detected.json")
        result = RegulationAnalysis.model_validate(fixture)

        for change in result.changes:
            assert isinstance(change.change_type, LawChangeType)

    def test_confidence_score_bounds(self):
        """Confidence score must be between 0.0 and 1.0."""
        fixture = _load_fixture("regulation_change_detected.json")
        # Modify to have invalid confidence
        fixture["changes"][0]["confidence_score"] = 1.5

        with pytest.raises(ValidationError):
            RegulationAnalysis.model_validate(fixture)

    def test_invalid_change_type_rejected(self):
        """Invalid change_type value should fail validation."""
        fixture = _load_fixture("regulation_change_detected.json")
        fixture["changes"][0]["change_type"] = "INVALID_TYPE"

        with pytest.raises(ValidationError):
            RegulationAnalysis.model_validate(fixture)


class TestKnownFunctions:
    """Tests for the KNOWN_FUNCTIONS list."""

    def test_contains_core_functions(self):
        assert "calc_income_tax" in KNOWN_FUNCTIONS
        assert "calc_salary_income_deduction" in KNOWN_FUNCTIONS
        assert "calc_basic_deduction" in KNOWN_FUNCTIONS
        assert "calc_furusato_limit" in KNOWN_FUNCTIONS

    def test_functions_not_hardcoded_in_templates(self):
        """Function names should NOT be hardcoded in prompt templates (single source of truth)."""
        from src.domain.prompts import (
            REGULATION_PARSE_PROMPT,
            REGULATION_PARSE_PROMPT_FIRST_SNAPSHOT,
        )

        for fn in KNOWN_FUNCTIONS:
            assert fn not in REGULATION_PARSE_PROMPT, (
                f"{fn} is hardcoded in REGULATION_PARSE_PROMPT; "
                "should only come from KNOWN_FUNCTIONS via placeholder"
            )
            assert fn not in REGULATION_PARSE_PROMPT_FIRST_SNAPSHOT, (
                f"{fn} is hardcoded in REGULATION_PARSE_PROMPT_FIRST_SNAPSHOT; "
                "should only come from KNOWN_FUNCTIONS via placeholder"
            )
