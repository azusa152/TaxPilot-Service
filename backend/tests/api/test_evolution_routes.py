"""Tests for api/evolution_routes.py — Evolution Loop admin API endpoints."""

import pytest

from src.domain.enums import AlgorithmStatus, EvolutionRunStatus, ReviewDecision
from src.infrastructure.models import AlgorithmRegistry, EvolutionRun, GenerationAttempt


class TestPostRun:
    """Tests for POST /admin/evolution/run."""

    async def test_starts_new_evolution_run(self, client, monkeypatch):
        """POST /admin/evolution/run should trigger the pipeline."""
        from unittest.mock import AsyncMock, MagicMock

        # Mock the entire start_run method
        mock_run = MagicMock()
        mock_run.id = 1
        mock_run.status = EvolutionRunStatus.AWAITING_REVIEW

        mock_pipeline = AsyncMock()
        mock_pipeline.start_run = AsyncMock(return_value=mock_run)

        monkeypatch.setattr(
            "src.api.evolution_routes.EvolutionPipeline",
            lambda db: mock_pipeline
        )

        response = await client.post("/admin/evolution/run")
        assert response.status_code == 200

        data = response.json()
        assert data["run_id"] == 1
        assert data["status"] == EvolutionRunStatus.AWAITING_REVIEW

    async def test_starts_run_with_specific_snapshot(self, client, monkeypatch):
        """POST /admin/evolution/run?snapshot_id=123 should use specific snapshot."""
        from unittest.mock import AsyncMock, MagicMock

        mock_run = MagicMock()
        mock_run.id = 1
        mock_run.status = EvolutionRunStatus.AWAITING_REVIEW

        mock_pipeline = AsyncMock()
        mock_pipeline.start_run = AsyncMock(return_value=mock_run)

        monkeypatch.setattr(
            "src.api.evolution_routes.EvolutionPipeline",
            lambda db: mock_pipeline
        )

        response = await client.post("/admin/evolution/run?snapshot_id=123")
        assert response.status_code == 200

        mock_pipeline.start_run.assert_called_once_with(
            trigger="MANUAL", snapshot_id=123
        )


class TestGetRuns:
    """Tests for GET /admin/evolution/runs."""

    async def test_lists_all_runs(self, client, db_session):
        """GET /admin/evolution/runs should return list of runs."""
        run1 = EvolutionRun(
            trigger="MANUAL",
            status=EvolutionRunStatus.AWAITING_REVIEW,
        )
        run2 = EvolutionRun(
            trigger="SCHEDULED",
            status=EvolutionRunStatus.ACCEPTED,
        )
        db_session.add_all([run1, run2])
        await db_session.flush()

        response = await client.get("/admin/evolution/runs")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 2
        assert data[0]["trigger"] == "SCHEDULED"  # Ordered by started_at desc
        assert data[1]["trigger"] == "MANUAL"

    async def test_filters_by_status(self, client, db_session):
        """GET /admin/evolution/runs?status=AWAITING_REVIEW should filter."""
        run1 = EvolutionRun(
            trigger="MANUAL",
            status=EvolutionRunStatus.AWAITING_REVIEW,
        )
        run2 = EvolutionRun(
            trigger="SCHEDULED",
            status=EvolutionRunStatus.ACCEPTED,
        )
        db_session.add_all([run1, run2])
        await db_session.flush()

        response = await client.get(
            "/admin/evolution/runs?status=AWAITING_REVIEW"
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == EvolutionRunStatus.AWAITING_REVIEW

    async def test_paginates_results(self, client, db_session):
        """GET /admin/evolution/runs?limit=2&offset=1 should paginate."""
        for i in range(5):
            run = EvolutionRun(trigger="MANUAL", status=EvolutionRunStatus.PENDING)
            db_session.add(run)
        await db_session.flush()

        response = await client.get("/admin/evolution/runs?limit=2&offset=1")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 2


class TestGetRun:
    """Tests for GET /admin/evolution/runs/{run_id}."""

    async def test_returns_run_details(self, client, db_session):
        """GET /admin/evolution/runs/1 should return detailed view."""
        run = EvolutionRun(
            trigger="MANUAL",
            status=EvolutionRunStatus.AWAITING_REVIEW,
            parsed_changes={"changes": [{"change_type": "THRESHOLD_UPDATE"}]},
        )
        db_session.add(run)
        await db_session.flush()

        # Add generation attempt
        attempt = GenerationAttempt(
            evolution_run_id=run.id,
            attempt_number=1,
            generated_code="def calc_test(): return 42",
            validation_passed=True,
        )
        db_session.add(attempt)
        await db_session.flush()

        response = await client.get(f"/admin/evolution/runs/{run.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == run.id
        assert data["trigger"] == "MANUAL"
        assert data["status"] == EvolutionRunStatus.AWAITING_REVIEW
        assert len(data["generation_attempts"]) == 1
        assert data["generation_attempts"][0]["attempt_number"] == 1

    async def test_returns_404_for_nonexistent_run(self, client):
        """GET /admin/evolution/runs/999 should return 404."""
        response = await client.get("/admin/evolution/runs/999")
        assert response.status_code == 404


class TestPostReview:
    """Tests for POST /admin/evolution/runs/{run_id}/review."""

    async def test_accepts_review_decision(self, client, db_session):
        """POST /admin/evolution/runs/1/review with ACCEPT decision."""
        # Create DRAFT algorithm
        draft_algo = AlgorithmRegistry(
            function_name="calc_basic_deduction",
            version="2024.01.01",
            code_content="def calc_basic_deduction(income):\n    return 500_000",
            status=AlgorithmStatus.DRAFT,
        )
        db_session.add(draft_algo)

        run = EvolutionRun(
            trigger="MANUAL",
            status=EvolutionRunStatus.AWAITING_REVIEW,
            parsed_changes={
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
            },
        )
        db_session.add(run)
        await db_session.flush()

        # Add generation attempt
        attempt = GenerationAttempt(
            evolution_run_id=run.id,
            attempt_number=1,
            generated_code="def calc_basic_deduction(income):\n    return 500_000",
            validation_passed=True,
        )
        db_session.add(attempt)
        await db_session.flush()

        response = await client.post(
            f"/admin/evolution/runs/{run.id}/review",
            json={
                "decision": ReviewDecision.ACCEPT,
                "rationale": "Looks good",
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["run_id"] == run.id
        assert data["status"] == EvolutionRunStatus.ACCEPTED

    async def test_rejects_review_for_wrong_status(self, client, db_session):
        """POST review should fail if run is not in AWAITING_REVIEW."""
        run = EvolutionRun(
            trigger="MANUAL",
            status=EvolutionRunStatus.ACCEPTED,  # Already accepted
        )
        db_session.add(run)
        await db_session.flush()

        response = await client.post(
            f"/admin/evolution/runs/{run.id}/review",
            json={
                "decision": ReviewDecision.ACCEPT,
                "rationale": "Test",
            },
        )
        assert response.status_code == 500  # Internal error


class TestPostRollback:
    """Tests for POST /admin/evolution/runs/{run_id}/rollback."""

    async def test_rollback_restores_previous_version(self, client, db_session):
        """POST /admin/evolution/runs/1/rollback should restore previous algo."""
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

        run = EvolutionRun(
            trigger="MANUAL",
            status=EvolutionRunStatus.ACCEPTED,
            activated_algorithm_id=active_algo.id,
        )
        db_session.add(run)
        await db_session.flush()

        response = await client.post(
            f"/admin/evolution/runs/{run.id}/rollback"
        )
        assert response.status_code == 200

        data = response.json()
        assert "Rollback completed" in data["message"]

        # Verify algorithm statuses were swapped
        await db_session.refresh(active_algo)
        await db_session.refresh(archived_algo)
        assert active_algo.status == AlgorithmStatus.ARCHIVED
        assert archived_algo.status == AlgorithmStatus.ACTIVE


class TestGetDeferred:
    """Tests for GET /admin/evolution/deferred."""

    async def test_lists_only_deferred_runs(self, client, db_session):
        """GET /admin/evolution/deferred should return only DEFERRED runs."""
        deferred_run = EvolutionRun(
            trigger="MANUAL",
            status=EvolutionRunStatus.DEFERRED,
        )
        accepted_run = EvolutionRun(
            trigger="MANUAL",
            status=EvolutionRunStatus.ACCEPTED,
        )
        db_session.add_all([deferred_run, accepted_run])
        await db_session.flush()

        response = await client.get("/admin/evolution/deferred")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == EvolutionRunStatus.DEFERRED

    async def test_returns_empty_list_when_no_deferred(self, client):
        """GET /admin/evolution/deferred should return empty list if none."""
        response = await client.get("/admin/evolution/deferred")
        assert response.status_code == 200

        data = response.json()
        assert data == []
