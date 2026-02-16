"""Tests for application/evolution_service.py — Evolution Pipeline orchestration."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.evolution_service import EvolutionPipeline
from src.domain.enums import (
    AlgorithmStatus,
    EvolutionRunStatus,
    LawChangeType,
    ReviewDecision,
)
from src.domain.schemas import LawChange, ReviewRequest
from src.infrastructure.models import (
    AlgorithmRegistry,
    AuditLog,
    EvolutionRun,
    GenerationAttempt,
)


class TestStartRun:
    """Tests for start_run() — full pipeline orchestration."""

    async def test_orchestrates_full_pipeline(self, db_session, monkeypatch):
        """start_run should orchestrate: crawl → parse → generate → AWAITING_REVIEW."""
        # Create NTA snapshot for FK constraint
        from src.infrastructure.models import NtaPageSnapshot, NtaTargetPage
        target_page = NtaTargetPage(
            name="income_tax_rates",
            url="https://example.com/test",
            description="Test page",
        )
        db_session.add(target_page)
        await db_session.flush()

        snapshot = NtaPageSnapshot(
            target_page_id=target_page.id,
            status="SUCCESS",
            content_hash="test_hash",
            fit_markdown="# Test content",
        )
        db_session.add(snapshot)
        await db_session.flush()

        # Mock NtaMonitor.check_for_changes
        mock_change = MagicMock()
        mock_change.snapshot_id = snapshot.id
        mock_monitor = AsyncMock()
        mock_monitor.check_for_changes = AsyncMock(return_value=[mock_change])

        # Mock RegulationParser.parse
        mock_analysis = MagicMock()
        mock_analysis.no_changes_detected = False
        mock_analysis.changes = [
            LawChange(
                change_type=LawChangeType.THRESHOLD_UPDATE,
                affected_function="calc_basic_deduction",
                old_value="480000",
                new_value="500000",
                description="Basic deduction increased",
                confidence_score=0.95,
            )
        ]
        mock_analysis.model_dump = MagicMock(return_value={"changes": []})
        mock_parser = AsyncMock()
        mock_parser.parse = AsyncMock(return_value=mock_analysis)

        # Mock CodeGenerator.generate
        mock_code_gen = AsyncMock()
        mock_code_gen.generate = AsyncMock()

        # Patch dependencies
        monkeypatch.setattr(
            "src.application.evolution_service.NtaMonitor",
            lambda db: mock_monitor
        )
        monkeypatch.setattr(
            "src.application.evolution_service.RegulationParser",
            lambda llm, db: mock_parser
        )
        monkeypatch.setattr(
            "src.application.evolution_service.CodeGenerator",
            lambda llm, db: mock_code_gen
        )
        monkeypatch.setattr(
            "src.application.evolution_service.SchemaGenerator",
            lambda llm, db: AsyncMock()
        )

        pipeline = EvolutionPipeline(db_session)
        run = await pipeline.start_run(trigger="MANUAL")

        assert run.status == EvolutionRunStatus.AWAITING_REVIEW
        assert run.nta_snapshot_id == 1
        mock_monitor.check_for_changes.assert_called_once()
        mock_parser.parse.assert_called_once()
        mock_code_gen.generate.assert_called_once()

    async def test_creates_child_runs_for_multiple_changes(self, db_session, monkeypatch):
        """When multiple pages change, create separate runs for each."""
        # Create NTA snapshots for FK constraints
        from src.infrastructure.models import NtaPageSnapshot, NtaTargetPage
        target_page = NtaTargetPage(
            name="income_tax_rates",
            url="https://example.com/test",
            description="Test page",
        )
        db_session.add(target_page)
        await db_session.flush()

        snapshot1 = NtaPageSnapshot(
            target_page_id=target_page.id,
            status="SUCCESS",
            content_hash="test_hash1",
            fit_markdown="# Test content 1",
        )
        snapshot2 = NtaPageSnapshot(
            target_page_id=target_page.id,
            status="SUCCESS",
            content_hash="test_hash2",
            fit_markdown="# Test content 2",
        )
        db_session.add_all([snapshot1, snapshot2])
        await db_session.flush()

        mock_change1 = MagicMock()
        mock_change1.snapshot_id = snapshot1.id
        mock_change2 = MagicMock()
        mock_change2.snapshot_id = snapshot2.id

        mock_monitor = AsyncMock()
        mock_monitor.check_for_changes = AsyncMock(return_value=[mock_change1, mock_change2])

        mock_analysis = MagicMock()
        mock_analysis.no_changes_detected = False
        mock_analysis.changes = [
            LawChange(
                change_type=LawChangeType.THRESHOLD_UPDATE,
                affected_function="calc_basic_deduction",
                old_value="480000",
                new_value="500000",
                description="Test",
                confidence_score=0.95,
            )
        ]
        mock_analysis.model_dump = MagicMock(return_value={"changes": []})
        mock_parser = AsyncMock()
        mock_parser.parse = AsyncMock(return_value=mock_analysis)

        monkeypatch.setattr(
            "src.application.evolution_service.NtaMonitor",
            lambda db: mock_monitor
        )
        monkeypatch.setattr(
            "src.application.evolution_service.RegulationParser",
            lambda llm, db: mock_parser
        )
        monkeypatch.setattr(
            "src.application.evolution_service.CodeGenerator",
            lambda llm, db: AsyncMock()
        )
        monkeypatch.setattr(
            "src.application.evolution_service.SchemaGenerator",
            lambda llm, db: AsyncMock()
        )

        pipeline = EvolutionPipeline(db_session)
        run = await pipeline.start_run(trigger="MANUAL")

        # Should create 2 runs total (parent + 1 child)
        # Parent processes snapshot 1, child processes snapshot 2
        assert run.nta_snapshot_id == 1

    async def test_handles_no_changes_detected(self, db_session, monkeypatch):
        """When crawler detects no changes, mark run as FAILED."""
        mock_monitor = AsyncMock()
        mock_monitor.check_for_changes = AsyncMock(return_value=[])

        monkeypatch.setattr(
            "src.application.evolution_service.NtaMonitor",
            lambda db: mock_monitor
        )

        pipeline = EvolutionPipeline(db_session)
        run = await pipeline.start_run(trigger="MANUAL")

        assert run.status == EvolutionRunStatus.FAILED
        assert run.error_message == "No changes detected"
        assert run.completed_at is not None

    async def test_handles_no_tax_rule_changes(self, db_session, monkeypatch):
        """When page changes but no tax rules detected, mark as FAILED."""
        # Create NTA snapshot for FK constraint
        from src.infrastructure.models import NtaPageSnapshot, NtaTargetPage
        target_page = NtaTargetPage(
            name="income_tax_rates",
            url="https://example.com/test",
            description="Test page",
        )
        db_session.add(target_page)
        await db_session.flush()

        snapshot = NtaPageSnapshot(
            target_page_id=target_page.id,
            status="SUCCESS",
            content_hash="test_hash",
            fit_markdown="# Test content",
        )
        db_session.add(snapshot)
        await db_session.flush()

        mock_change = MagicMock()
        mock_change.snapshot_id = snapshot.id
        mock_monitor = AsyncMock()
        mock_monitor.check_for_changes = AsyncMock(return_value=[mock_change])

        mock_analysis = MagicMock()
        mock_analysis.no_changes_detected = True
        mock_analysis.model_dump = MagicMock(return_value={})
        mock_parser = AsyncMock()
        mock_parser.parse = AsyncMock(return_value=mock_analysis)

        monkeypatch.setattr(
            "src.application.evolution_service.NtaMonitor",
            lambda db: mock_monitor
        )
        monkeypatch.setattr(
            "src.application.evolution_service.RegulationParser",
            lambda llm, db: mock_parser
        )

        pipeline = EvolutionPipeline(db_session)
        run = await pipeline.start_run(trigger="MANUAL")

        assert run.status == EvolutionRunStatus.FAILED
        assert "no tax rule changes detected" in run.error_message.lower()
        assert run.completed_at is not None

    async def test_handles_pipeline_failure(self, db_session, monkeypatch):
        """When any step fails, mark run as FAILED with error message."""
        mock_monitor = AsyncMock()
        mock_monitor.check_for_changes = AsyncMock(side_effect=Exception("Crawler error"))

        monkeypatch.setattr(
            "src.application.evolution_service.NtaMonitor",
            lambda db: mock_monitor
        )

        pipeline = EvolutionPipeline(db_session)
        run = await pipeline.start_run(trigger="MANUAL")

        assert run.status == EvolutionRunStatus.FAILED
        assert "Crawler error" in run.error_message
        assert run.completed_at is not None


class TestSubmitReview:
    """Tests for submit_review() — all 4 decision paths."""

    async def test_accept_activates_draft_algorithm(self, db_session, evolution_run):
        """ACCEPT decision should activate the DRAFT algorithm."""
        # Create a DRAFT algorithm for the test
        draft_algo = AlgorithmRegistry(
            function_name="calc_basic_deduction",
            version="2024.01.01",
            code_content="def calc_basic_deduction(income):\n    return 500_000",
            status=AlgorithmStatus.DRAFT,
        )
        db_session.add(draft_algo)
        await db_session.flush()

        # Create a generation attempt for the run
        attempt = GenerationAttempt(
            evolution_run_id=evolution_run.id,
            attempt_number=1,
            generated_code="def calc_basic_deduction(income):\n    return 500_000",
            validation_passed=True,
        )
        db_session.add(attempt)

        # Set run to AWAITING_REVIEW with parsed changes
        evolution_run.status = EvolutionRunStatus.AWAITING_REVIEW
        evolution_run.parsed_changes = {
            "changes": [
                {
                    "change_type": "THRESHOLD_UPDATE",
                    "affected_function": "calc_basic_deduction",
                    "old_value": "480000",
                    "new_value": "500000",
                    "description": "Test",
                    "confidence_score": 0.95,
                }
            ]
        }
        await db_session.flush()

        pipeline = EvolutionPipeline(db_session)
        review = ReviewRequest(
            decision=ReviewDecision.ACCEPT,
            rationale="Looks good",
        )

        run = await pipeline.submit_review(evolution_run.id, review, actor="admin")

        assert run.status == EvolutionRunStatus.ACCEPTED
        assert run.review_decision == ReviewDecision.ACCEPT
        assert run.rationale == "Looks good"
        assert run.completed_at is not None
        assert run.activated_algorithm_id == draft_algo.id

        # Check audit log was created
        from sqlalchemy import select
        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "REVIEW_ACCEPTED")
        )
        audit_log = result.scalar_one()
        assert audit_log.actor == "admin"
        assert audit_log.target_id == str(run.id)

    async def test_modify_validates_and_activates_custom_code(self, db_session, evolution_run):
        """MODIFY decision should validate admin code and activate it."""
        evolution_run.status = EvolutionRunStatus.AWAITING_REVIEW
        evolution_run.parsed_changes = {
            "changes": [
                {
                    "change_type": "THRESHOLD_UPDATE",
                    "affected_function": "calc_basic_deduction",
                    "old_value": "480000",
                    "new_value": "500000",
                    "description": "Test",
                    "confidence_score": 0.95,
                }
            ]
        }
        await db_session.flush()

        custom_code = "def calc_basic_deduction(income):\n    return 510_000"

        pipeline = EvolutionPipeline(db_session)
        review = ReviewRequest(
            decision=ReviewDecision.MODIFY,
            rationale="Need to adjust the value",
            modified_code=custom_code,
        )

        run = await pipeline.submit_review(evolution_run.id, review, actor="admin")

        assert run.status == EvolutionRunStatus.MODIFIED
        assert run.review_decision == ReviewDecision.MODIFY
        assert run.modified_code == custom_code
        assert run.completed_at is not None

        # Check audit log
        from sqlalchemy import select
        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "REVIEW_MODIFIED")
        )
        audit_log = result.scalar_one()
        assert audit_log.actor == "admin"

    async def test_modify_rejects_invalid_code(self, db_session, evolution_run):
        """MODIFY decision should reject code that fails validation."""
        evolution_run.status = EvolutionRunStatus.AWAITING_REVIEW
        evolution_run.parsed_changes = {"changes": []}
        await db_session.flush()

        invalid_code = "def calc_basic_deduction(income):\n    import os\n    return 500_000"

        pipeline = EvolutionPipeline(db_session)
        review = ReviewRequest(
            decision=ReviewDecision.MODIFY,
            rationale="Custom code",
            modified_code=invalid_code,
        )

        with pytest.raises(ValueError, match="failed validation"):
            await pipeline.submit_review(evolution_run.id, review, actor="admin")

    async def test_regenerate_calls_llm_with_hints(self, db_session, evolution_run, monkeypatch):
        """REGENERATE decision should call LLM again with admin hints."""
        evolution_run.status = EvolutionRunStatus.AWAITING_REVIEW
        evolution_run.regeneration_count = 0
        evolution_run.parsed_changes = {
            "changes": [
                {
                    "change_type": "THRESHOLD_UPDATE",
                    "affected_function": "calc_basic_deduction",
                    "old_value": "480000",
                    "new_value": "500000",
                    "description": "Test",
                    "confidence_score": 0.95,
                }
            ]
        }
        await db_session.flush()

        mock_code_gen = AsyncMock()
        mock_code_gen.generate = AsyncMock()
        monkeypatch.setattr(
            "src.application.evolution_service.CodeGenerator",
            lambda llm, db: mock_code_gen
        )

        pipeline = EvolutionPipeline(db_session)
        review = ReviewRequest(
            decision=ReviewDecision.REGENERATE,
            rationale="Need better logic",
            regeneration_hints="Use integer division",
        )

        run = await pipeline.submit_review(evolution_run.id, review, actor="admin")

        assert run.status == EvolutionRunStatus.AWAITING_REVIEW
        assert run.regeneration_count == 1
        assert run.regeneration_hints == "Use integer division"
        mock_code_gen.generate.assert_called_once()

    async def test_regenerate_enforces_max_attempts(self, db_session, evolution_run):
        """REGENERATE should fail after max_regenerations attempts."""
        evolution_run.status = EvolutionRunStatus.AWAITING_REVIEW
        evolution_run.regeneration_count = 3
        evolution_run.max_regenerations = 3
        await db_session.flush()

        pipeline = EvolutionPipeline(db_session)
        review = ReviewRequest(
            decision=ReviewDecision.REGENERATE,
            rationale="Try again",
        )

        with pytest.raises(ValueError, match="Maximum regeneration attempts"):
            await pipeline.submit_review(evolution_run.id, review, actor="admin")

    async def test_skip_permanent_marks_skipped(self, db_session, evolution_run):
        """SKIP_PERMANENT decision should mark run as SKIPPED."""
        evolution_run.status = EvolutionRunStatus.AWAITING_REVIEW
        await db_session.flush()

        pipeline = EvolutionPipeline(db_session)
        review = ReviewRequest(
            decision=ReviewDecision.SKIP_PERMANENT,
            rationale="Not applicable",
            skip_reason="This change doesn't affect our users",
        )

        run = await pipeline.submit_review(evolution_run.id, review, actor="admin")

        assert run.status == EvolutionRunStatus.SKIPPED
        assert run.review_decision == ReviewDecision.SKIP_PERMANENT
        assert run.completed_at is not None

        # Check audit log
        from sqlalchemy import select
        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "REVIEW_SKIPPED_PERMANENT")
        )
        audit_log = result.scalar_one()
        assert audit_log.actor == "admin"

    async def test_skip_manual_marks_deferred(self, db_session, evolution_run):
        """SKIP_MANUAL decision should mark run as DEFERRED."""
        evolution_run.status = EvolutionRunStatus.AWAITING_REVIEW
        await db_session.flush()

        pipeline = EvolutionPipeline(db_session)
        review = ReviewRequest(
            decision=ReviewDecision.SKIP_MANUAL,
            rationale="Handle later",
            skip_reason="Need more time to review",
        )

        run = await pipeline.submit_review(evolution_run.id, review, actor="admin")

        assert run.status == EvolutionRunStatus.DEFERRED
        assert run.review_decision == ReviewDecision.SKIP_MANUAL
        assert run.completed_at is not None

        # Check audit log
        from sqlalchemy import select
        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "REVIEW_DEFERRED")
        )
        audit_log = result.scalar_one()
        assert audit_log.actor == "admin"


class TestRollback:
    """Tests for rollback() — restore previous algorithm version."""

    async def test_rollback_restores_previous_version(self, db_session, evolution_run):
        """rollback should re-activate the previous ARCHIVED algorithm."""
        # Create current ACTIVE algorithm
        active_algo = AlgorithmRegistry(
            function_name="calc_basic_deduction",
            version="2024.02.01",
            code_content="def calc_basic_deduction(income):\n    return 500_000",
            status=AlgorithmStatus.ACTIVE,
        )
        db_session.add(active_algo)

        # Create previous ARCHIVED algorithm
        archived_algo = AlgorithmRegistry(
            function_name="calc_basic_deduction",
            version="2024.01.01",
            code_content="def calc_basic_deduction(income):\n    return 480_000",
            status=AlgorithmStatus.ARCHIVED,
        )
        db_session.add(archived_algo)

        evolution_run.activated_algorithm_id = active_algo.id
        await db_session.flush()

        pipeline = EvolutionPipeline(db_session)
        await pipeline.rollback(evolution_run.id, actor="admin")

        await db_session.refresh(active_algo)
        await db_session.refresh(archived_algo)

        assert active_algo.status == AlgorithmStatus.ARCHIVED
        assert archived_algo.status == AlgorithmStatus.ACTIVE

        # Check audit log
        from sqlalchemy import select
        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "ALGORITHM_ROLLBACK")
        )
        audit_log = result.scalar_one()
        assert audit_log.actor == "admin"
        assert "rolled_back_from" in audit_log.details
        assert "rolled_back_to" in audit_log.details

    async def test_rollback_fails_without_previous_version(self, db_session, evolution_run):
        """rollback should fail if no previous ARCHIVED version exists."""
        # Create only one ACTIVE algorithm with no previous version
        active_algo = AlgorithmRegistry(
            function_name="calc_basic_deduction",
            version="2024.01.01",
            code_content="def calc_basic_deduction(income):\n    return 500_000",
            status=AlgorithmStatus.ACTIVE,
        )
        db_session.add(active_algo)

        evolution_run.activated_algorithm_id = active_algo.id
        await db_session.flush()

        pipeline = EvolutionPipeline(db_session)

        with pytest.raises(ValueError, match="No previous version to rollback"):
            await pipeline.rollback(evolution_run.id, actor="admin")
