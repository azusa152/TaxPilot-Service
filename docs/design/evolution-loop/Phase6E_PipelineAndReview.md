# Phase 6E: Pipeline Orchestration & Admin Review

**Goal:** Wire all components into an end-to-end pipeline with a rich admin approval flow (4 decision paths), full audit trail, rollback capability, and hot-reload.

**Depends on:** All previous phases (6A through 6D, plus 6-Pre for baseline data)
**Produces:** `EvolutionPipeline` orchestrator, enhanced Streamlit admin dashboard with review UI, 4-option approval flow, audit trail, rollback capability

---

## Context

Phases 6A–6D and 6-Pre have built the individual components:
- **6A:** LLM Gateway (`LlmService`)
- **6B:** NTA Crawler (`NtaMonitor`)
- **6C:** Regulation Parser (`RegulationParser`)
- **6D:** Code & Schema Generator (`CodeGenerator`, `SchemaGenerator`, `CodeSandbox`)
- **6-Pre:** Bootstrap (populated `AlgorithmRegistry`, baseline snapshots)

This phase **orchestrates** them into a single pipeline and provides the admin with a rich review and decision interface. The admin has 4 options for each generated formula, and every action is logged to an audit trail.

### Admin Approval Decision Tree

```
Pipeline generates new formula
         |
    Admin Review
    /    |     \      \
ACCEPT  MODIFY  REGEN  SKIP
  |       |       |      |
  v       v       v      +-- SKIP_PERMANENT (ignored)
Activate  Validate  LLM    +-- SKIP_MANUAL (deferred)
          via       retry
          Sandbox   (max 3)
  |       |       |
  v       v       v
  ACTIVE  ACTIVE  GENERATING → AWAITING_REVIEW (loop)
```

| Decision | Action | DB Status |
|----------|--------|-----------|
| **ACCEPT** | Activate algorithm, archive previous, apply schema | `ACCEPTED` |
| **MODIFY** | Admin edits code → `CodeSandbox.validate()` → activate | `MODIFIED` |
| **REGENERATE** | Call LLM again with admin hints (max 3 attempts) | `REGENERATING` → `GENERATING` |
| **SKIP_PERMANENT** | Ignore this regulation change permanently | `SKIPPED` |
| **SKIP_MANUAL** | Defer for manual handling later | `DEFERRED` |

### EvolutionRun Status Transitions

```
PENDING → CRAWLING → PARSING → GENERATING → AWAITING_REVIEW
                                                  |
                         +----------+-------------+----------+
                         |          |             |          |
                      ACCEPTED   MODIFIED   REGENERATING  SKIPPED
                         |          |             |          |
                         v          v             v          +→ DEFERRED
                       (done)     (done)    → GENERATING
                                              (loop back,
                                               max 3 times)

Also: FAILED (if any step errors out)
```

---

## Tasks

### Task 6E.1: Enums

**File:** `backend/src/domain/enums.py`

```python
class EvolutionRunStatus(str, Enum):
    """Status of an evolution pipeline run."""
    PENDING = "PENDING"
    CRAWLING = "CRAWLING"
    PARSING = "PARSING"
    GENERATING = "GENERATING"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    ACCEPTED = "ACCEPTED"
    MODIFIED = "MODIFIED"
    REGENERATING = "REGENERATING"
    SKIPPED = "SKIPPED"
    DEFERRED = "DEFERRED"
    FAILED = "FAILED"


class ReviewDecision(str, Enum):
    """Admin's review decision for a generated formula."""
    ACCEPT = "ACCEPT"
    MODIFY = "MODIFY"
    REGENERATE = "REGENERATE"
    SKIP_PERMANENT = "SKIP_PERMANENT"
    SKIP_MANUAL = "SKIP_MANUAL"
```

### Task 6E.2: Update EvolutionRun Model

**File:** `backend/src/infrastructure/models.py`

Update the `EvolutionRun` table (created in Phase 6C) with review workflow fields:

```python
class EvolutionRun(Base):
    """Tracks an end-to-end evolution pipeline run."""
    __tablename__ = "evolution_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    nta_snapshot_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("nta_page_snapshots.id"), nullable=True
    )
    parsed_changes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Review workflow fields (Phase 6E)
    review_decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    modified_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    regeneration_hints: Mapped[str | None] = mapped_column(Text, nullable=True)
    regeneration_count: Mapped[int] = mapped_column(Integer, default=0)
    max_regenerations: Mapped[int] = mapped_column(Integer, default=3)
    activated_algorithm_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("algorithm_registry.id"), nullable=True
    )
    schema_proposal_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("schema_change_proposals.id"), nullable=True
    )

    __table_args__ = (
        Index("ix_evolution_runs_status", "status"),
        Index("ix_evolution_runs_created_at", "created_at"),
    )
```

### Task 6E.3: Audit Log Model

**File:** `backend/src/infrastructure/models.py`

```python
class AuditLog(Base):
    """Immutable audit trail for all significant admin actions."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # e.g., "ALGORITHM_ACTIVATED", "REVIEW_DECISION"
    actor: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # admin username or "system"
    target_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # e.g., "AlgorithmRegistry", "EvolutionRun"
    target_id: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # ID of the affected entity
    details: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # action-specific context
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_audit_logs_target", "target_type", "target_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )
```

### Task 6E.4: Review Request Schema

**File:** `backend/src/domain/schemas.py`

```python
class ReviewRequest(BaseModel):
    """Admin review decision for an evolution run."""
    decision: str = Field(
        description="Review decision: ACCEPT, MODIFY, REGENERATE, SKIP_PERMANENT, SKIP_MANUAL"
    )
    rationale: str = Field(
        description="Reason for the decision (required for all decisions)"
    )
    modified_code: str | None = Field(
        None,
        description="Admin-provided code (required when decision=MODIFY)"
    )
    regeneration_hints: str | None = Field(
        None,
        description="Hints for the LLM to improve generation (optional, used when decision=REGENERATE)"
    )
    skip_reason: str | None = Field(
        None,
        description="Reason for skipping (optional, used when decision=SKIP_*)"
    )


class EvolutionRunDetail(BaseModel):
    """Detailed view of an evolution run including generated artifacts."""
    id: int
    trigger: str
    status: str
    nta_snapshot_id: int | None
    parsed_changes: dict | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
    review_decision: str | None
    rationale: str | None
    regeneration_count: int
    max_regenerations: int
    generation_attempts: list[dict] = Field(
        default_factory=list,
        description="All code generation attempts for this run"
    )
    schema_proposal: dict | None = Field(
        None, description="Proposed schema changes (if any)"
    )

    model_config = {"from_attributes": True}


class EvolutionRunSummary(BaseModel):
    """Summary view of an evolution run for list endpoints."""
    id: int
    trigger: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    review_decision: str | None

    model_config = {"from_attributes": True}
```

### Task 6E.5: Evolution Service (Application Layer)

**File:** `backend/src/application/evolution_service.py`

Orchestrates the full pipeline and handles all 4 decision paths:

```python
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import AlgorithmStatus, EvolutionRunStatus, ReviewDecision
from src.domain.schemas import ReviewRequest
from src.infrastructure.code_generator import CodeGenerator
from src.infrastructure.code_sandbox import CodeSandbox
from src.infrastructure.llm_service import LlmService
from src.infrastructure.models import (
    AlgorithmRegistry,
    AuditLog,
    EvolutionRun,
    GenerationAttempt,
    NtaPageSnapshot,
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
        run = EvolutionRun(trigger=trigger, status="PENDING")
        self.db.add(run)
        await self.db.flush()

        try:
            # Step 1: Get snapshot (crawl or use provided)
            run.status = "CRAWLING"
            await self.db.flush()

            if snapshot_id:
                run.nta_snapshot_id = snapshot_id
            else:
                monitor = NtaMonitor(self.db)
                changes = await monitor.check_for_changes(trigger=trigger)
                if not changes:
                    run.status = "FAILED"
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
            run.status = "PARSING"
            await self.db.flush()

            llm = LlmService(self.db)
            parser = RegulationParser(llm, self.db)
            analysis = await parser.parse(
                snapshot_id=run.nta_snapshot_id,
                evolution_run_id=run.id,
            )
            run.parsed_changes = analysis.model_dump()

            if analysis.no_changes_detected:
                run.status = "FAILED"
                run.error_message = "Page changed but no tax rule changes detected"
                run.completed_at = datetime.now(timezone.utc)
                await self.db.flush()
                return run

            # Step 3: Generate code and schema
            run.status = "GENERATING"
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
            run.status = "AWAITING_REVIEW"
            await self.db.flush()

        except Exception as e:
            run.status = "FAILED"
            run.error_message = str(e)
            run.completed_at = datetime.now(timezone.utc)
            logger.error(f"Evolution run {run.id} failed: {e}")

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
        if run.status != "AWAITING_REVIEW":
            raise ValueError(
                f"Run {run_id} is in status {run.status}, expected AWAITING_REVIEW"
            )

        run.review_decision = review.decision
        run.rationale = review.rationale

        if review.decision == ReviewDecision.ACCEPT.value:
            await self._handle_accept(run, actor)

        elif review.decision == ReviewDecision.MODIFY.value:
            if not review.modified_code:
                raise ValueError("modified_code is required for MODIFY decision")
            await self._handle_modify(run, review.modified_code, actor)

        elif review.decision == ReviewDecision.REGENERATE.value:
            await self._handle_regenerate(run, review.regeneration_hints, actor)

        elif review.decision == ReviewDecision.SKIP_PERMANENT.value:
            run.status = "SKIPPED"
            run.completed_at = datetime.now(timezone.utc)
            await self._log_audit(
                "REVIEW_SKIPPED_PERMANENT", actor, "EvolutionRun", str(run.id),
                {"rationale": review.rationale, "skip_reason": review.skip_reason},
            )

        elif review.decision == ReviewDecision.SKIP_MANUAL.value:
            run.status = "DEFERRED"
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

        run.status = "ACCEPTED"
        run.completed_at = datetime.now(timezone.utc)

        await self._log_audit(
            "REVIEW_ACCEPTED", actor, "EvolutionRun", str(run.id),
            {"rationale": run.rationale},
        )

    async def _handle_modify(
        self, run: EvolutionRun, modified_code: str, actor: str
    ) -> None:
        """Accept with admin-provided modifications."""
        # Validate the admin's code through the same sandbox
        validation = CodeSandbox.validate(code=modified_code)
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

        run.status = "MODIFIED"
        run.completed_at = datetime.now(timezone.utc)

        await self._log_audit(
            "REVIEW_MODIFIED", actor, "EvolutionRun", str(run.id),
            {"rationale": run.rationale, "code_modified": True},
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
        run.status = "REGENERATING"

        await self._log_audit(
            "REVIEW_REGENERATE", actor, "EvolutionRun", str(run.id),
            {
                "rationale": run.rationale,
                "hints": hints,
                "attempt": run.regeneration_count,
            },
        )

        # Re-run code generation with hints
        # (This triggers the GENERATING → AWAITING_REVIEW flow again)
        llm = LlmService(self.db)
        code_gen = CodeGenerator(llm, self.db)

        changes = run.parsed_changes.get("changes", []) if run.parsed_changes else []
        for change_data in changes:
            from src.domain.schemas import LawChange
            change = LawChange(**change_data)

            current_algo = await self._get_current_algorithm(change.affected_function)
            current_code = current_algo.code_content if current_algo else ""

            await code_gen.generate(
                law_change=change,
                current_code=current_code,
                evolution_run_id=run.id,
                attempt_number=run.regeneration_count + 1,
                admin_hints=hints or "",
            )

        run.status = "AWAITING_REVIEW"

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
                AlgorithmRegistry.status == "ARCHIVED",
            )
            .order_by(AlgorithmRegistry.id.desc())
            .limit(1)
        )
        prev_algo = result.scalar_one_or_none()
        if prev_algo is None:
            raise ValueError(f"No previous version to rollback to for {algo.function_name}")

        # Swap: current ACTIVE → ARCHIVED, previous ARCHIVED → ACTIVE
        algo.status = "ARCHIVED"
        prev_algo.status = "ACTIVE"

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
                AlgorithmRegistry.status == "ACTIVE",
            )
        )
        return result.scalar_one_or_none()

    async def _get_current_profile_fields(self) -> dict:
        """Get current ProfileDefinition fields as a dict."""
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

    async def _activate_draft_algorithm(
        self, run: EvolutionRun, actor: str
    ) -> int:
        """Find the DRAFT algorithm for this run and activate it."""
        # Implementation: find DRAFT, archive current ACTIVE, set DRAFT → ACTIVE
        pass

    async def _activate_modified_algorithm(
        self, run: EvolutionRun, code: str, actor: str
    ) -> int:
        """Create and activate an algorithm from admin-modified code."""
        # Implementation: create new AlgorithmRegistry entry, activate it
        pass

    async def _apply_schema_proposal(self, run: EvolutionRun) -> None:
        """Apply the schema change proposal if one exists."""
        # Implementation: update ProfileDefinition for the relevant year
        pass

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
```

### Task 6E.6: API Routes

**File:** `backend/src/api/evolution_routes.py`

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.evolution_service import EvolutionPipeline
from src.domain.schemas import (
    EvolutionRunDetail,
    EvolutionRunSummary,
    ReviewRequest,
)
from src.infrastructure.database import get_db

router = APIRouter(prefix="/admin/evolution", tags=["Admin - Evolution Loop"])


@router.post(
    "/run",
    summary="Start a new evolution pipeline run",
)
async def start_evolution_run(
    snapshot_id: int | None = Query(
        None, description="Specific snapshot to process (optional)"
    ),
    db: AsyncSession = Depends(get_db),
):
    pipeline = EvolutionPipeline(db)
    run = await pipeline.start_run(trigger="MANUAL", snapshot_id=snapshot_id)
    return {"run_id": run.id, "status": run.status}


@router.get(
    "/runs",
    response_model=list[EvolutionRunSummary],
    summary="List all evolution runs with optional status filter",
)
async def list_runs(
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    # Query EvolutionRun with optional status filter
    pass


@router.get(
    "/runs/{run_id}",
    response_model=EvolutionRunDetail,
    summary="Get detailed view of an evolution run",
)
async def get_run(run_id: int, db: AsyncSession = Depends(get_db)):
    # Get run with generation attempts and schema proposal
    pass


@router.post(
    "/runs/{run_id}/review",
    summary="Submit admin review decision",
)
async def submit_review(
    run_id: int,
    review: ReviewRequest,
    db: AsyncSession = Depends(get_db),
):
    pipeline = EvolutionPipeline(db)
    run = await pipeline.submit_review(run_id, review, actor="admin")
    return {"run_id": run.id, "status": run.status}


@router.post(
    "/runs/{run_id}/rollback",
    summary="Rollback to previous algorithm version",
)
async def rollback_run(
    run_id: int, db: AsyncSession = Depends(get_db)
):
    pipeline = EvolutionPipeline(db)
    await pipeline.rollback(run_id, actor="admin")
    return {"message": f"Rollback completed for run {run_id}"}


@router.get(
    "/deferred",
    response_model=list[EvolutionRunSummary],
    summary="List all deferred runs awaiting manual handling",
)
async def list_deferred(db: AsyncSession = Depends(get_db)):
    # Query runs with status=DEFERRED
    pass
```

**Update `backend/src/main.py`:**

```python
from src.api.evolution_routes import router as evolution_router

# Inside create_app():
application.include_router(evolution_router)
```

### Task 6E.7: Streamlit Admin Page — Evolution Review

**File:** `admin/app.py` (new page)

The "Evolution Review" page provides:

**1. Run Overview:**
- List of all evolution runs with status, trigger, timestamps
- Status filter tabs: All / Awaiting Review / Active / Deferred / Failed
- Click to open detailed review view

**2. Detailed Review View (for AWAITING_REVIEW runs):**

- **Side-by-side diff:** Current algorithm code vs proposed code (syntax highlighted)
- **Schema proposal section:** New/changed fields highlighted with descriptions
- **LLM analysis summary:** Parsed regulation changes with confidence scores
- **NTA markdown link:** Click to view the stored `fit_markdown` that triggered this

**3. Decision Panel (4 buttons):**

- **Accept** button — one-click acceptance
  - Confirmation dialog: "Activate this formula? The current version will be archived."

- **Modify** button — opens inline code editor
  - Monaco-style code editor (or Streamlit `st.code_editor`) pre-filled with generated code
  - Admin edits the code
  - "Validate & Activate" button runs `CodeSandbox.validate()` and shows result
  - Validation errors shown inline; must pass before activation

- **Regenerate** button — opens hints panel
  - Text area for admin to provide hints/corrections
  - Shows attempt count (e.g., "Attempt 2 of 3")
  - "Regenerate" button sends hints to LLM
  - Disabled after max attempts reached

- **Skip** button — opens sub-options
  - Radio: "Permanent skip (ignore)" vs "Handle manually later (defer)"
  - Reason text field (required)
  - "Skip" confirmation button

**4. Generation Attempt History:**
- Timeline of all attempts for this run (if regenerated)
- Each attempt shows: generated code, validation result, admin hints, timestamp
- Compare different attempts side-by-side

**5. Deferred Tasks Tab:**
- List of all DEFERRED runs awaiting manual handling
- Each entry shows: run details, original regulation change, reason for deferral
- "Resolve" button to reopen the review flow

**6. Audit Trail Tab:**
- Chronological log of all actions for this run
- Who did what, when, and why (decision + rationale)

**7. Cost Dashboard:**
- LLM token usage and cost per run
- Monthly totals across all runs
- Budget remaining indicator

### Task 6E.8: Alembic Migration

```bash
alembic revision --autogenerate -m "update evolution_runs with review fields, add audit_logs table"
```

---

## Security

- **Admin authentication** required for all `/admin/evolution/` endpoints
- All review decisions logged to `AuditLog` with admin identity, decision, and rationale
- **MODIFY path:** Admin-provided code passes through the **same** `CodeSandbox.validate()` as LLM-generated code — no bypass
- Activation triggers hot-reload via `AlgorithmLoader`; previous version **archived (never deleted)**
- Schema changes applied only after ACCEPT or MODIFY; old `ProfileDefinition` preserved with version
- **Rate limiting** on evolution runs (max N per day configurable) to prevent runaway LLM costs
- Max regeneration attempts **enforced server-side** (prevents infinite LLM cost loop)
- Rollback is always available — previous algorithm versions are preserved

---

## Test Specification

Per `testing-policy.md`, every task must ship with tests.

### Unit Tests (`tests/application/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_evolution_pipeline.py` | `EvolutionPipeline` | run() orchestrates crawl→parse→generate→PENDING_REVIEW, processes ALL changed pages (not just first), handles failure at each step gracefully (marks run FAILED), submit_review() for each decision: ACCEPT activates code, MODIFY validates custom code via sandbox, REGENERATE calls LLM with hints (max 3 retries), SKIP_PERMANENT marks SKIPPED, SKIP_MANUAL marks DEFERRED, rollback() restores previous algorithm version |

### Unit Tests (`tests/infrastructure/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_audit_log.py` | `AuditLog` model | Audit entries created for all review decisions, entries include actor, action, rationale |

### Integration Tests (`tests/api/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_evolution_routes.py` | API endpoints | `POST /admin/evolution/run` triggers pipeline, `GET /admin/evolution/runs` lists runs with pagination, `POST /admin/evolution/runs/{id}/review` accepts review decisions, `POST /admin/evolution/runs/{id}/rollback` restores previous version |

### Test Conventions
- Mock `NtaMonitor`, `RegulationParser`, `CodeGenerator`, `SchemaGenerator` — test orchestration logic only.
- Use factory fixtures for `EvolutionRun` in each status.
- Test state transitions exhaustively (e.g., PENDING_REVIEW → ACCEPTED, PENDING_REVIEW → REGENERATING).

---

## Acceptance Criteria

1. `POST /admin/evolution/run` triggers the full pipeline (crawl → parse → generate → await review) and returns a run ID.
2. Admin can **Accept**, **Modify**, **Regenerate**, or **Skip** via API and Streamlit UI.
3. **ACCEPT:** New algorithm is activated, previous archived, schema proposal applied.
4. **MODIFY:** Admin-edited code passes `CodeSandbox.validate()`, then is activated.
5. **REGENERATE:** LLM is called again with admin hints; new attempt stored; max 3 retries enforced.
6. **SKIP_PERMANENT:** Run marked `SKIPPED`; no further action needed.
7. **SKIP_MANUAL:** Run marked `DEFERRED`; appears in "Deferred Tasks" list.
8. All decisions appear in `AuditLog` with actor, action, and rationale.
9. Rollback restores previous algorithm and schema definition.
10. Side-by-side code diff is displayed in Streamlit for easy review.
11. Generation attempt history shows all attempts (including regenerations) for a run.
