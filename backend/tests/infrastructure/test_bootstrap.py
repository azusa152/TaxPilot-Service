"""Tests for infrastructure/bootstrap.py — BootstrapRunner."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from src.domain.enums import AlgorithmStatus, VerificationStatus
from src.domain.schemas import VerificationResult
from src.infrastructure.bootstrap import (
    FUNCTIONS_TO_REGISTER,
    NTA_TARGET_PAGES,
    BootstrapRunner,
)
from src.infrastructure.models import (
    AlgorithmRegistry,
    BootstrapVerificationReport,
    NtaPageSnapshot,
    NtaTargetPage,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / "llm_responses" / name).read_text())


class TestStep1BaselineCrawl:
    """Tests for BootstrapRunner._step1_baseline_crawl()."""

    async def test_seeds_all_target_pages(self, db_session):
        """Step 1 should seed all NTA target pages."""
        runner = BootstrapRunner(db=db_session)
        result = await runner._step1_baseline_crawl(skip_crawl=True)

        assert result["pages_seeded"] == len(NTA_TARGET_PAGES)

        pages = (await db_session.execute(select(NtaTargetPage))).scalars().all()
        assert len(pages) == len(NTA_TARGET_PAGES)

    async def test_seed_is_idempotent(self, db_session):
        """Re-running seed should not create duplicate pages."""
        runner = BootstrapRunner(db=db_session)
        await runner._step1_baseline_crawl(skip_crawl=True)
        result = await runner._step1_baseline_crawl(skip_crawl=True)

        assert result["pages_seeded"] == 0

        pages = (await db_session.execute(select(NtaTargetPage))).scalars().all()
        assert len(pages) == len(NTA_TARGET_PAGES)

    async def test_skip_crawl_returns_zero_crawled(self, db_session):
        """skip_crawl=True should not attempt crawling."""
        runner = BootstrapRunner(db=db_session)
        result = await runner._step1_baseline_crawl(skip_crawl=True)

        assert result["pages_crawled"] == 0
        assert result["crawl"] == "skipped"

    @patch("src.infrastructure.bootstrap.NtaMonitor")
    async def test_crawl_invokes_nta_monitor(self, mock_monitor_class, db_session):
        """When not skipping crawl, NtaMonitor.check_for_changes is called."""
        mock_monitor = AsyncMock()
        mock_monitor.check_for_changes = AsyncMock(return_value=[])
        mock_monitor_class.return_value = mock_monitor

        runner = BootstrapRunner(db=db_session)
        result = await runner._step1_baseline_crawl(skip_crawl=False)

        mock_monitor.check_for_changes.assert_awaited_once()
        assert result["pages_crawled"] == 0


class TestStep2SeedRegistry:
    """Tests for BootstrapRunner._step2_seed_registry()."""

    async def test_registers_all_9_functions(self, db_session):
        """Step 2 should register all 9 known functions as ACTIVE."""
        runner = BootstrapRunner(db=db_session)
        result = await runner._step2_seed_registry()

        assert result["registered"] == 9
        assert result["skipped"] == 0

        algos = (await db_session.execute(select(AlgorithmRegistry))).scalars().all()
        assert len(algos) == 9

        func_names = {a.function_name for a in algos}
        assert func_names == set(FUNCTIONS_TO_REGISTER)

    async def test_all_registered_as_active(self, db_session):
        """All registered algorithms should be ACTIVE with version 2024.1."""
        runner = BootstrapRunner(db=db_session)
        await runner._step2_seed_registry()

        algos = (await db_session.execute(select(AlgorithmRegistry))).scalars().all()
        for algo in algos:
            assert algo.status == AlgorithmStatus.ACTIVE
            assert algo.version == "2024.1"

    async def test_code_content_contains_function_definition(self, db_session):
        """Each registered algorithm should contain its function definition."""
        runner = BootstrapRunner(db=db_session)
        await runner._step2_seed_registry()

        algos = (await db_session.execute(select(AlgorithmRegistry))).scalars().all()
        for algo in algos:
            assert f"def {algo.function_name}" in algo.code_content

    async def test_seed_is_idempotent(self, db_session):
        """Re-running seed should skip already-registered functions."""
        runner = BootstrapRunner(db=db_session)
        await runner._step2_seed_registry()
        result = await runner._step2_seed_registry()

        assert result["registered"] == 0
        assert result["skipped"] == 9

        algos = (await db_session.execute(select(AlgorithmRegistry))).scalars().all()
        assert len(algos) == 9

    async def test_source_law_hash_is_none_without_snapshots(self, db_session):
        """Without NTA snapshots, source_law_hash should be None."""
        runner = BootstrapRunner(db=db_session)
        await runner._step2_seed_registry()

        algos = (await db_session.execute(select(AlgorithmRegistry))).scalars().all()
        for algo in algos:
            assert algo.source_law_hash is None

    async def test_source_law_hash_populated_with_snapshots(self, db_session):
        """With NTA snapshots, source_law_hash should be set from snapshot content_hash."""
        # Seed a target page and snapshot
        page = NtaTargetPage(
            name="income_tax_rates",
            url="https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2260.htm",
            is_active=True,
        )
        db_session.add(page)
        await db_session.flush()

        snapshot = NtaPageSnapshot(
            target_page_id=page.id,
            content_hash="abc123hash",
            fit_markdown="# Tax rates",
            status="SUCCESS",
        )
        db_session.add(snapshot)
        await db_session.flush()

        runner = BootstrapRunner(db=db_session)
        await runner._step2_seed_registry()

        # calc_income_tax and calc_basic_deduction are sourced by income_tax_rates
        result = await db_session.execute(
            select(AlgorithmRegistry).where(
                AlgorithmRegistry.function_name == "calc_income_tax"
            )
        )
        algo = result.scalar_one()
        assert algo.source_law_hash == "abc123hash"


class TestStep3Verify:
    """Tests for BootstrapRunner._step3_verify()."""

    async def _setup_page_with_snapshot(self, db_session, page_name="income_tax_rates"):
        """Helper to create a target page with a SUCCESS snapshot."""
        page = NtaTargetPage(
            name=page_name,
            url=f"https://example.com/{page_name}",
            is_active=True,
        )
        db_session.add(page)
        await db_session.flush()

        snapshot = NtaPageSnapshot(
            target_page_id=page.id,
            content_hash="hash123",
            fit_markdown="# NTA regulation text for " + page_name,
            status="SUCCESS",
        )
        db_session.add(snapshot)
        await db_session.flush()
        return snapshot

    async def test_verify_calls_llm_for_each_function(self, db_session):
        """Verification should call LLM for each function mapped to a snapshot."""
        await self._setup_page_with_snapshot(db_session, "income_tax_rates")

        fixture = _load_fixture("verification_match.json")
        llm = AsyncMock()
        llm.generate_structured = AsyncMock(
            return_value=VerificationResult.model_validate(fixture)
        )

        runner = BootstrapRunner(db=db_session, llm_service=llm)
        result = await runner._step3_verify()

        # income_tax_rates maps to 2 functions: calc_income_tax, calc_basic_deduction
        assert llm.generate_structured.await_count == 2
        assert result["total"] == 2
        assert result["matched"] == 2

    async def test_verify_stores_reports(self, db_session):
        """Verification results should be stored in DB."""
        await self._setup_page_with_snapshot(db_session, "income_tax_rates")

        fixture = _load_fixture("verification_match.json")
        llm = AsyncMock()
        llm.generate_structured = AsyncMock(
            return_value=VerificationResult.model_validate(fixture)
        )

        runner = BootstrapRunner(db=db_session, llm_service=llm)
        await runner._step3_verify()

        reports = (
            await db_session.execute(select(BootstrapVerificationReport))
        ).scalars().all()
        assert len(reports) == 2
        assert all(r.verification_status == VerificationStatus.MATCH for r in reports)

    async def test_verify_mismatch_counted_correctly(self, db_session):
        """Mismatch results should be counted in the summary."""
        await self._setup_page_with_snapshot(db_session, "salary_deduction")

        fixture = _load_fixture("verification_mismatch.json")
        llm = AsyncMock()
        llm.generate_structured = AsyncMock(
            return_value=VerificationResult.model_validate(fixture)
        )

        runner = BootstrapRunner(db=db_session, llm_service=llm)
        result = await runner._step3_verify()

        # salary_deduction maps to 1 function
        assert result["total"] == 1
        assert result["mismatched"] == 1
        assert result["matched"] == 0

    async def test_verify_skips_pages_without_snapshots(self, db_session):
        """Pages without snapshots should be skipped."""
        # Add target page but no snapshot
        page = NtaTargetPage(
            name="income_tax_rates",
            url="https://example.com/test",
            is_active=True,
        )
        db_session.add(page)
        await db_session.flush()

        llm = AsyncMock()
        runner = BootstrapRunner(db=db_session, llm_service=llm)
        result = await runner._step3_verify()

        assert result["total"] == 0
        llm.generate_structured.assert_not_awaited()

    async def test_verify_sends_correct_prompt_content(self, db_session):
        """Verification prompt should include NTA content and function code."""
        await self._setup_page_with_snapshot(db_session, "salary_deduction")

        fixture = _load_fixture("verification_match.json")
        llm = AsyncMock()
        llm.generate_structured = AsyncMock(
            return_value=VerificationResult.model_validate(fixture)
        )

        runner = BootstrapRunner(db=db_session, llm_service=llm)
        await runner._step3_verify()

        call_args = llm.generate_structured.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "NTA regulation text for salary_deduction" in prompt
        assert "calc_salary_income_deduction" in prompt
        assert call_args.kwargs["caller"] == "bootstrap_verification"


class TestFullRun:
    """Tests for BootstrapRunner.run() end-to-end."""

    async def test_run_with_skip_crawl_and_verification(self, db_session):
        """Full run with both skips should seed pages and registry."""
        runner = BootstrapRunner(db=db_session)
        summary = await runner.run(skip_crawl=True, skip_verification=True)

        assert summary["step1_crawl"]["pages_seeded"] == len(NTA_TARGET_PAGES)
        assert summary["step2_seed"]["registered"] == 9
        assert summary["step3_verify"] == "skipped"

    async def test_run_is_idempotent(self, db_session):
        """Running bootstrap twice should not create duplicates."""
        runner = BootstrapRunner(db=db_session)
        await runner.run(skip_crawl=True, skip_verification=True)
        summary = await runner.run(skip_crawl=True, skip_verification=True)

        assert summary["step1_crawl"]["pages_seeded"] == 0
        assert summary["step2_seed"]["registered"] == 0
        assert summary["step2_seed"]["skipped"] == 9

    async def test_run_verification_only_requires_llm(self, db_session):
        """run_verification_only should raise if no LLM service."""
        runner = BootstrapRunner(db=db_session, llm_service=None)
        with pytest.raises(ValueError, match="LLM service is required"):
            await runner.run_verification_only()
