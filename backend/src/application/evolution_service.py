"""Evolution Pipeline service — orchestrates end-to-end pipeline with admin review."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.notification_manager import NotificationManager
from src.domain.enums import AlgorithmStatus, EvolutionRunStatus, LawChangeType, ReviewDecision
from src.domain.schemas import LawChange, ReviewRequest
from src.infrastructure.code_generator import CodeGenerator
from src.infrastructure.code_sandbox import CodeSandbox
from src.infrastructure.llm_service import LlmService
from src.infrastructure.models import (
    AlgorithmRegistry,
    AuditLog,
    EvolutionRun,
    GenerationAttempt,
)
from src.infrastructure.nta_monitor import NtaMonitor
from src.infrastructure.regulation_parser import RegulationParser
from src.infrastructure.schema_generator import SchemaGenerator
from src.logging_config import get_logger

logger = get_logger(__name__)


class EvolutionPipeline:
    """Orchestrates the end-to-end evolution pipeline.

    Pipeline flow:
    1. Crawl NTA pages for changes (or use a specific snapshot)
    2. Parse changes via RegulationParser
    3. Generate code + schema via CodeGenerator + SchemaGenerator
    4. Store as AWAITING_REVIEW
    5. Admin reviews and makes a decision
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.notifier = NotificationManager(db)

    async def start_run(
        self, trigger: str = "MANUAL", snapshot_id: int | None = None
    ) -> EvolutionRun:
        """Start a new evolution pipeline run.

        Args:
            trigger: "MANUAL" or "SCHEDULED"
            snapshot_id: Optional specific snapshot to process.
                If None, triggers a new crawl.

        Returns:
            The created EvolutionRun.
        """
        run = EvolutionRun(trigger=trigger, status=EvolutionRunStatus.PENDING)
        self.db.add(run)
        await self.db.flush()

        try:
            # Step 1: Get snapshot (crawl or use provided)
            run.status = EvolutionRunStatus.CRAWLING
            await self.db.flush()

            if snapshot_id:
                run.nta_snapshot_id = snapshot_id
            else:
                monitor = NtaMonitor(self.db)
                changes = await monitor.check_for_changes(trigger=trigger)
                if not changes:
                    run.status = EvolutionRunStatus.FAILED
                    run.error_message = "No changes detected"
                    run.completed_at = datetime.now(timezone.utc)
                    await self.db.flush()
                    return run

                # Process ALL detected changes — create child runs for multi-page changes
                if len(changes) > 1:
                    logger.info(
                        f"Detected {len(changes)} changed pages — "
                        f"creating child runs for each"
                    )
                    for extra_change in changes[1:]:
                        child_run = await self.start_run(
                            trigger=trigger,
                            snapshot_id=extra_change.snapshot_id,
                        )
                        logger.info(
                            f"Created child run {child_run.id} for "
                            f"snapshot {extra_change.snapshot_id}"
                        )

                # Process first change in current run
                run.nta_snapshot_id = changes[0].snapshot_id

            # Step 2: Parse regulation changes
            run.status = EvolutionRunStatus.PARSING
            await self.db.flush()

            llm = LlmService(self.db)
            parser = RegulationParser(llm, self.db)
            analysis = await parser.parse(
                snapshot_id=run.nta_snapshot_id,
                evolution_run_id=run.id,
            )
            run.parsed_changes = analysis.model_dump()

            if analysis.no_changes_detected:
                run.status = EvolutionRunStatus.FAILED
                run.error_message = "Page changed but no tax rule changes detected"
                run.completed_at = datetime.now(timezone.utc)
                await self.db.flush()
                return run

            # Step 3: Generate code and schema
            run.status = EvolutionRunStatus.GENERATING
            await self.db.flush()

            code_gen = CodeGenerator(llm, self.db)
            schema_gen = SchemaGenerator(llm, self.db)

            for change in analysis.changes:
                # Get current algorithm code
                current_algo = await self._get_current_algorithm(
                    change.affected_function
                )
                current_code = current_algo.code_content if current_algo else ""

                await code_gen.generate(
                    law_change=change,
                    current_code=current_code,
                    evolution_run_id=run.id,
                )

            # Generate schema proposal if needed
            new_field_changes = [
                c for c in analysis.changes
                if c.change_type == LawChangeType.NEW_FIELD_REQUIRED
            ]
            if new_field_changes:
                current_fields = await self._get_current_profile_fields()
                await schema_gen.generate(
                    changes=new_field_changes,
                    current_fields=current_fields,
                    evolution_run_id=run.id,
                )

            # Step 4: Await review
            run.status = EvolutionRunStatus.AWAITING_REVIEW
            await self.db.flush()

            # Notify: formula ready for review
            function_name = self._get_affected_function_name(run)
            change_summary = self._get_change_summary(run)
            await self.notifier.notify_formula_ready_for_review(
                run_id=run.id,
                function_name=function_name,
                change_summary=change_summary,
                dashboard_url=f"/admin/evolution/runs/{run.id}",
            )

        except Exception as e:
            run.status = EvolutionRunStatus.FAILED
            run.error_message = str(e)
            run.completed_at = datetime.now(timezone.utc)
            logger.exception(f"Evolution run {run.id} failed: {e}")

            # Notify: run failed
            await self.notifier.notify_run_failed(
                run_id=run.id,
                failed_step=run.status.value,
                error=str(e),
                dashboard_url=f"/admin/evolution/runs/{run.id}",
            )

        await self.db.flush()
        return run

    async def submit_review(
        self, run_id: int, review: ReviewRequest, actor: str = "admin"
    ) -> EvolutionRun:
        """Process an admin review decision.

        Args:
            run_id: ID of the evolution run.
            review: The admin's review decision and associated data.
            actor: Username of the reviewing admin.

        Returns:
            Updated EvolutionRun.
        """
        run = await self.db.get(EvolutionRun, run_id)
        if run is None:
            raise ValueError(f"Evolution run {run_id} not found")
        if run.status != EvolutionRunStatus.AWAITING_REVIEW:
            raise ValueError(
                f"Run {run_id} is in status {run.status}, expected AWAITING_REVIEW"
            )

        run.review_decision = review.decision
        run.rationale = review.rationale

        if review.decision == ReviewDecision.ACCEPT:
            await self._handle_accept(run, actor)

        elif review.decision == ReviewDecision.MODIFY:
            if not review.modified_code:
                raise ValueError("modified_code is required for MODIFY decision")
            await self._handle_modify(run, review.modified_code, actor)

        elif review.decision == ReviewDecision.REGENERATE:
            await self._handle_regenerate(run, review.regeneration_hints, actor)

        elif review.decision == ReviewDecision.SKIP_PERMANENT:
            run.status = EvolutionRunStatus.SKIPPED
            run.completed_at = datetime.now(timezone.utc)
            await self._log_audit(
                "REVIEW_SKIPPED_PERMANENT", actor, "EvolutionRun", str(run.id),
                {"rationale": review.rationale, "skip_reason": review.skip_reason},
            )

        elif review.decision == ReviewDecision.SKIP_MANUAL:
            run.status = EvolutionRunStatus.DEFERRED
            run.completed_at = datetime.now(timezone.utc)
            await self._log_audit(
                "REVIEW_DEFERRED", actor, "EvolutionRun", str(run.id),
                {"rationale": review.rationale, "skip_reason": review.skip_reason},
            )

        await self.db.flush()
        return run

    async def _handle_accept(self, run: EvolutionRun, actor: str) -> None:
        """Accept the generated formula as-is."""
        # Activate the DRAFT algorithm
        latest_attempt = await self._get_latest_attempt(run.id)
        if latest_attempt and latest_attempt.validation_passed:
            algo_id = await self._activate_draft_algorithm(run, actor)
            run.activated_algorithm_id = algo_id

        # Apply schema proposal if exists
        await self._apply_schema_proposal(run)

        run.status = EvolutionRunStatus.ACCEPTED
        run.completed_at = datetime.now(timezone.utc)

        await self._log_audit(
            "REVIEW_ACCEPTED", actor, "EvolutionRun", str(run.id),
            {"rationale": run.rationale},
        )

        # Notify: formula activated
        function_name = self._get_affected_function_name(run)
        algo = await self.db.get(AlgorithmRegistry, run.activated_algorithm_id)
        await self.notifier.notify_formula_activated(
            run_id=run.id,
            function_name=function_name,
            version=str(algo.id) if algo else "unknown",
            decision="ACCEPT",
            dashboard_url=f"/admin/evolution/runs/{run.id}",
        )

    async def _handle_modify(
        self, run: EvolutionRun, modified_code: str, actor: str
    ) -> None:
        """Accept with admin-provided modifications."""
        # Extract function name for validation
        function_name = self._get_affected_function_name(run)

        # Validate the admin's code through the same sandbox
        validation = CodeSandbox.validate(
            code=modified_code,
            expected_function_name=function_name,
        )
        if not validation.passed:
            raise ValueError(
                f"Admin-provided code failed validation: {validation.errors}"
            )

        run.modified_code = modified_code

        # Store as a new generation attempt
        attempt = GenerationAttempt(
            evolution_run_id=run.id,
            attempt_number=run.regeneration_count + 1,
            generated_code=modified_code,
            validation_passed=True,
            admin_hints="Admin-provided modification",
        )
        self.db.add(attempt)

        # Create and activate the algorithm
        algo_id = await self._activate_modified_algorithm(run, modified_code, actor)
        run.activated_algorithm_id = algo_id

        # Apply schema proposal if exists
        await self._apply_schema_proposal(run)

        run.status = EvolutionRunStatus.MODIFIED
        run.completed_at = datetime.now(timezone.utc)

        await self._log_audit(
            "REVIEW_MODIFIED", actor, "EvolutionRun", str(run.id),
            {"rationale": run.rationale, "code_modified": True},
        )

        # Notify: formula activated (with modifications)
        function_name = self._get_affected_function_name(run)
        algo = await self.db.get(AlgorithmRegistry, run.activated_algorithm_id)
        await self.notifier.notify_formula_activated(
            run_id=run.id,
            function_name=function_name,
            version=str(algo.id) if algo else "unknown",
            decision="MODIFY",
            dashboard_url=f"/admin/evolution/runs/{run.id}",
        )

    async def _handle_regenerate(
        self, run: EvolutionRun, hints: str | None, actor: str
    ) -> None:
        """Request LLM regeneration with optional admin hints."""
        if run.regeneration_count >= run.max_regenerations:
            raise ValueError(
                f"Maximum regeneration attempts ({run.max_regenerations}) reached"
            )

        run.regeneration_hints = hints
        run.regeneration_count += 1
        run.status = EvolutionRunStatus.REGENERATING

        await self._log_audit(
            "REVIEW_REGENERATE", actor, "EvolutionRun", str(run.id),
            {
                "rationale": run.rationale,
                "hints": hints,
                "attempt": run.regeneration_count,
            },
        )

        # Re-run code generation with hints
        llm = LlmService(self.db)
        code_gen = CodeGenerator(llm, self.db)

        changes = run.parsed_changes.get("changes", []) if run.parsed_changes else []
        for change_data in changes:
            try:
                change = LawChange.model_validate(change_data)
            except Exception as e:
                raise ValueError(
                    f"Failed to deserialize LawChange from parsed_changes: {e}"
                ) from e

            current_algo = await self._get_current_algorithm(change.affected_function)
            current_code = current_algo.code_content if current_algo else ""

            await code_gen.generate(
                law_change=change,
                current_code=current_code,
                evolution_run_id=run.id,
                attempt_number=run.regeneration_count + 1,
                admin_hints=hints or "",
            )

        run.status = EvolutionRunStatus.AWAITING_REVIEW

        # Notify: formula regenerating
        await self.notifier.notify_formula_regenerating(
            run_id=run.id,
            attempt=run.regeneration_count,
            max_attempts=run.max_regenerations,
            hints=hints,
            dashboard_url=f"/admin/evolution/runs/{run.id}",
        )

    async def rollback(self, run_id: int, actor: str = "admin") -> None:
        """Rollback to the previous algorithm version.

        Re-activates the ARCHIVED version and archives the current ACTIVE.
        """
        run = await self.db.get(EvolutionRun, run_id)
        if run is None or run.activated_algorithm_id is None:
            raise ValueError(f"No activated algorithm to rollback for run {run_id}")

        # Get the activated algorithm
        algo = await self.db.get(AlgorithmRegistry, run.activated_algorithm_id)
        if algo is None:
            raise ValueError("Activated algorithm not found")

        # Find the previous archived version
        result = await self.db.execute(
            select(AlgorithmRegistry)
            .where(
                AlgorithmRegistry.function_name == algo.function_name,
                AlgorithmRegistry.status == AlgorithmStatus.ARCHIVED,
            )
            .order_by(AlgorithmRegistry.id.desc())
            .limit(1)
        )
        prev_algo = result.scalar_one_or_none()
        if prev_algo is None:
            raise ValueError(f"No previous version to rollback to for {algo.function_name}")

        # Swap: current ACTIVE → ARCHIVED, previous ARCHIVED → ACTIVE
        algo.status = AlgorithmStatus.ARCHIVED
        prev_algo.status = AlgorithmStatus.ACTIVE

        await self._log_audit(
            "ALGORITHM_ROLLBACK", actor, "AlgorithmRegistry", str(algo.id),
            {
                "rolled_back_from": f"{algo.function_name} v{algo.version}",
                "rolled_back_to": f"{prev_algo.function_name} v{prev_algo.version}",
                "evolution_run_id": run_id,
            },
        )

        await self.db.flush()
        logger.info(
            f"Rolled back {algo.function_name}: v{algo.version} → v{prev_algo.version}"
        )

    # --- Helper methods ---

    async def _get_current_algorithm(self, function_name: str) -> AlgorithmRegistry | None:
        result = await self.db.execute(
            select(AlgorithmRegistry).where(
                AlgorithmRegistry.function_name == function_name,
                AlgorithmRegistry.status == AlgorithmStatus.ACTIVE,
            )
        )
        return result.scalar_one_or_none()

    async def _get_current_profile_fields(self) -> dict:
        """Get current ProfileDefinition fields as a dict.

        For MVP, returns the 2024 definition. In production, would query
        ProfileDefinition table for the latest version.
        """
        from src.domain.constants import PROFILE_DEFINITION_2024
        return PROFILE_DEFINITION_2024

    async def _get_latest_attempt(self, run_id: int) -> GenerationAttempt | None:
        result = await self.db.execute(
            select(GenerationAttempt)
            .where(GenerationAttempt.evolution_run_id == run_id)
            .order_by(GenerationAttempt.attempt_number.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def _get_affected_function_name(self, run: EvolutionRun) -> str:
        """Extract the affected function name from parsed changes.

        Raises:
            ValueError: If no changes found or no affected_function specified.
        """
        changes = run.parsed_changes.get("changes", []) if run.parsed_changes else []
        if not changes:
            raise ValueError(f"No parsed changes found for run {run.id}")

        function_name = changes[0].get("affected_function")
        if not function_name:
            raise ValueError("No affected_function in parsed changes")

        return function_name

    def _get_change_summary(self, run: EvolutionRun) -> str:
        """Generate a brief summary of the law changes for notification.

        Args:
            run: EvolutionRun with parsed_changes

        Returns:
            Summary string like "2024 threshold update (¥2M → ¥2.4M)"
        """
        changes = run.parsed_changes.get("changes", []) if run.parsed_changes else []
        if not changes:
            return "Unknown change"

        first_change = changes[0]
        change_type = first_change.get("change_type", "UNKNOWN")
        summary = first_change.get("summary", "")

        if len(changes) == 1:
            return f"{change_type}: {summary}"
        else:
            return f"{change_type}: {summary} (+{len(changes) - 1} more)"

    async def _activate_draft_algorithm(
        self, run: EvolutionRun, actor: str
    ) -> int:
        """Find the DRAFT algorithm for this run and activate it.

        Archives the current ACTIVE version and activates the DRAFT.
        """
        # Find DRAFT algorithm from latest generation attempt
        latest_attempt = await self._get_latest_attempt(run.id)
        if not latest_attempt:
            raise ValueError(f"No generation attempt found for run {run.id}")

        # Extract function name from parsed changes
        function_name = self._get_affected_function_name(run)

        # Find the DRAFT algorithm for this function
        result = await self.db.execute(
            select(AlgorithmRegistry)
            .where(
                AlgorithmRegistry.function_name == function_name,
                AlgorithmRegistry.status == AlgorithmStatus.DRAFT,
            )
            .order_by(AlgorithmRegistry.id.desc())
            .limit(1)
        )
        draft_algo = result.scalar_one_or_none()
        if not draft_algo:
            raise ValueError(f"No DRAFT algorithm found for {function_name}")

        # Archive current ACTIVE version
        current_active = await self._get_current_algorithm(function_name)
        if current_active:
            current_active.status = AlgorithmStatus.ARCHIVED
            await self._log_audit(
                "ALGORITHM_ARCHIVED", actor, "AlgorithmRegistry", str(current_active.id),
                {"function_name": function_name, "version": current_active.version},
            )

        # Activate the DRAFT
        draft_algo.status = AlgorithmStatus.ACTIVE
        await self._log_audit(
            "ALGORITHM_ACTIVATED", actor, "AlgorithmRegistry", str(draft_algo.id),
            {
                "function_name": function_name,
                "version": draft_algo.version,
                "evolution_run_id": run.id,
            },
        )

        logger.info(f"Activated algorithm {function_name} v{draft_algo.version}")
        return draft_algo.id

    async def _activate_modified_algorithm(
        self, run: EvolutionRun, code: str, actor: str
    ) -> int:
        """Create and activate an algorithm from admin-modified code."""
        # Extract function name from parsed changes
        function_name = self._get_affected_function_name(run)

        # Archive current ACTIVE version
        current_active = await self._get_current_algorithm(function_name)
        if current_active:
            current_active.status = AlgorithmStatus.ARCHIVED
            await self._log_audit(
                "ALGORITHM_ARCHIVED", actor, "AlgorithmRegistry", str(current_active.id),
                {"function_name": function_name, "version": current_active.version},
            )

        # Create new ACTIVE algorithm from modified code
        # Version format: YYYY.MM.DD-NN where NN is sequence number
        from datetime import datetime
        today = datetime.now(timezone.utc)
        base_version = today.strftime("%Y.%m.%d")

        # Find the highest sequence number for today
        result = await self.db.execute(
            select(AlgorithmRegistry)
            .where(AlgorithmRegistry.function_name == function_name)
            .where(AlgorithmRegistry.version.like(f"{base_version}-%"))
            .order_by(AlgorithmRegistry.version.desc())
            .limit(1)
        )
        latest_today = result.scalar_one_or_none()

        if latest_today:
            # Extract sequence number and increment
            seq = int(latest_today.version.split("-")[-1]) + 1
        else:
            seq = 1

        new_version = f"{base_version}-{seq:02d}"

        new_algo = AlgorithmRegistry(
            function_name=function_name,
            version=new_version,
            code_content=code,
            status=AlgorithmStatus.ACTIVE,
            source_law_hash=None,  # TODO: Link to NTA snapshot if needed
        )
        self.db.add(new_algo)
        await self.db.flush()

        await self._log_audit(
            "ALGORITHM_ACTIVATED", actor, "AlgorithmRegistry", str(new_algo.id),
            {
                "function_name": function_name,
                "version": new_version,
                "evolution_run_id": run.id,
                "modified_by_admin": True,
            },
        )

        logger.info(f"Activated modified algorithm {function_name} v{new_version}")
        return new_algo.id

    async def _apply_schema_proposal(self, run: EvolutionRun) -> None:
        """Apply the schema change proposal if one exists.

        For MVP, this logs the proposed changes. In production, this would
        update the ProfileDefinition table and trigger schema migration.
        """
        if run.schema_proposal_id is None:
            return

        # TODO: Implement schema application logic
        # For MVP, just log that a schema proposal exists
        await self._log_audit(
            "SCHEMA_PROPOSAL_NOTED", "system", "EvolutionRun", str(run.id),
            {"schema_proposal_id": run.schema_proposal_id},
        )
        logger.info(f"Schema proposal {run.schema_proposal_id} noted for run {run.id}")

    async def _log_audit(
        self,
        action: str,
        actor: str,
        target_type: str,
        target_id: str,
        details: dict | None = None,
    ) -> None:
        """Write an entry to the audit log."""
        log = AuditLog(
            action=action,
            actor=actor,
            target_type=target_type,
            target_id=target_id,
            details=details,
        )
        self.db.add(log)
        await self.db.flush()
