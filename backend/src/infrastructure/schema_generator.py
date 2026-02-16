"""Schema generator — determines if new user input fields are needed.

Generates SchemaChangeProposal objects via structured LLM output based on
identified law changes. Proposals are stored as PENDING for admin review.
"""

import json

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import ProposalStatus
from src.domain.exceptions import LlmCallError
from src.domain.prompts import SCHEMA_GENERATION_PROMPT
from src.domain.schemas import LawChange, SchemaChangeProposal
from src.infrastructure.llm_service import LlmService
from src.infrastructure.models import SchemaChangeProposalRecord
from src.logging_config import get_logger

logger = get_logger(__name__)


class SchemaGenerator:
    """Determines if new user input fields are needed based on law changes.

    Generates SchemaChangeProposal objects via structured LLM output.
    """

    def __init__(self, llm_service: LlmService, db: AsyncSession):
        self.llm = llm_service
        self.db = db

    async def generate(
        self,
        changes: list[LawChange],
        current_fields: dict,
        evolution_run_id: int,
    ) -> SchemaChangeProposal:
        """Generate a schema change proposal from law changes.

        Args:
            changes: List of identified law changes.
            current_fields: Current ProfileDefinition fields as a dict.
            evolution_run_id: ID of the evolution run for tracking.

        Returns:
            SchemaChangeProposal with new/modified/removed fields.

        Raises:
            LlmCallError: If the LLM call fails (logged before re-raise).
        """
        changes_json = json.dumps(
            [c.model_dump() for c in changes], indent=2
        )

        prompt = SCHEMA_GENERATION_PROMPT.format(
            changes_json=changes_json,
            current_fields=json.dumps(current_fields, indent=2),
        )

        try:
            result = await self.llm.generate_structured(
                messages=[{"role": "user", "content": prompt}],
                response_format=SchemaChangeProposal,
                caller="schema_generator",
                evolution_run_id=evolution_run_id,
            )
        except LlmCallError:
            logger.error(
                f"LLM call failed during schema generation for evolution run {evolution_run_id}"
            )
            raise

        # Store the proposal in DB
        record = SchemaChangeProposalRecord(
            evolution_run_id=evolution_run_id,
            year=result.year,
            proposal_data=result.model_dump(),
            status=ProposalStatus.PENDING,
        )
        self.db.add(record)
        await self.db.flush()

        logger.info(
            f"Schema proposal for year {result.year}: "
            f"{len(result.new_fields)} new fields, "
            f"{len(result.removed_fields)} removed fields"
        )
        return result
