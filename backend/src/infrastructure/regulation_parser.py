"""Regulation parser — extracts structured law changes from NTA snapshots.

Uses LlmService with Pydantic response_format for validated structured output.
Compares current and previous snapshot fit_markdown to identify tax rule changes.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import SnapshotStatus
from src.domain.exceptions import NotFoundError
from src.domain.prompts import (
    REGULATION_PARSE_PROMPT,
    REGULATION_PARSE_PROMPT_FIRST_SNAPSHOT,
)
from src.domain.schemas import RegulationAnalysis
from src.infrastructure.llm_service import LlmService
from src.infrastructure.models import NtaPageSnapshot
from src.logging_config import get_logger

logger = get_logger(__name__)

# Known calculation functions included in the prompt context
KNOWN_FUNCTIONS = [
    "calc_salary_income_deduction",
    "calc_basic_deduction",
    "calc_income_tax",
    "calc_spouse_deduction",
    "calc_dependents_deduction",
    "calc_social_insurance_deduction",
    "calc_life_insurance_deduction",
    "calc_ideco_deduction",
    "calc_furusato_limit",
]


class RegulationParser:
    """Parses NTA page content into structured law change descriptions.

    Uses stored fit_markdown from NtaPageSnapshot (not raw HTML).
    Sends to LLM via LlmService with response_format=RegulationAnalysis
    for structured, validated output.
    """

    def __init__(self, llm_service: LlmService, db: AsyncSession):
        self.llm = llm_service
        self.db = db

    async def parse(
        self,
        snapshot_id: int,
        evolution_run_id: int | None = None,
    ) -> RegulationAnalysis:
        """Parse a snapshot's content into structured regulation changes.

        Args:
            snapshot_id: ID of the NtaPageSnapshot to parse.
            evolution_run_id: Optional link to the evolution run for cost tracking.

        Returns:
            RegulationAnalysis with identified changes.

        Raises:
            NotFoundError: If snapshot not found or has no fit_markdown.
        """
        snapshot = await self.db.get(NtaPageSnapshot, snapshot_id)
        if snapshot is None:
            raise NotFoundError(f"Snapshot {snapshot_id} not found")
        if not snapshot.fit_markdown:
            raise NotFoundError(
                f"Snapshot {snapshot_id} has no fit_markdown (status may be FAILED)"
            )

        # Get the previous successful snapshot for comparison
        prev_result = await self.db.execute(
            select(NtaPageSnapshot)
            .where(
                NtaPageSnapshot.target_page_id == snapshot.target_page_id,
                NtaPageSnapshot.id < snapshot.id,
                NtaPageSnapshot.status == SnapshotStatus.SUCCESS,
            )
            .order_by(NtaPageSnapshot.fetched_at.desc())
            .limit(1)
        )
        prev_snapshot = prev_result.scalar_one_or_none()

        # Build the prompt based on whether we have a previous snapshot
        functions_text = "\n".join(f"- {fn}" for fn in KNOWN_FUNCTIONS)
        if prev_snapshot and prev_snapshot.fit_markdown:
            prompt = REGULATION_PARSE_PROMPT.format(
                new_content=snapshot.fit_markdown,
                old_content=prev_snapshot.fit_markdown,
                known_functions=functions_text,
            )
        else:
            prompt = REGULATION_PARSE_PROMPT_FIRST_SNAPSHOT.format(
                content=snapshot.fit_markdown,
                known_functions=functions_text,
            )

        # Call LLM with structured output
        # TODO(Phase 6E): Add retry-once logic and EvolutionRun status update
        # on failure. Currently, LlmCallError propagates to the caller.
        result = await self.llm.generate_structured(
            messages=[{"role": "user", "content": prompt}],
            response_format=RegulationAnalysis,
            caller="regulation_parser",
            evolution_run_id=evolution_run_id,
        )

        logger.info(
            f"Parsed snapshot {snapshot_id}: {len(result.changes)} changes found, "
            f"no_changes={result.no_changes_detected}"
        )
        return result
