"""LLM-assisted code generation for tax calculation functions.

Generates updated Python code from law change descriptions using LiteLLM
structured output. Validates all generated code via CodeSandbox before
storing as DRAFT in AlgorithmRegistry.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import AlgorithmStatus
from src.domain.exceptions import LlmCallError
from src.domain.prompts import CODE_GENERATION_PROMPT
from src.domain.schemas import CodeGenerationResult, LawChange
from src.infrastructure.code_sandbox import CodeSandbox
from src.infrastructure.llm_service import LlmService
from src.infrastructure.models import AlgorithmRegistry, GenerationAttempt
from src.logging_config import get_logger

logger = get_logger(__name__)


class CodeGenerator:
    """Generates updated tax calculation code from law changes.

    Uses LLM via LlmService with structured output for reliable code generation.
    Validates all generated code via CodeSandbox before storing as DRAFT.
    """

    def __init__(self, llm_service: LlmService, db: AsyncSession):
        self.llm = llm_service
        self.db = db

    async def generate(
        self,
        law_change: LawChange,
        current_code: str,
        evolution_run_id: int,
        attempt_number: int = 1,
        admin_hints: str = "",
    ) -> tuple[CodeGenerationResult, bool]:
        """Generate updated code for a law change.

        Args:
            law_change: The structured law change to implement.
            current_code: Current source code of the affected function.
            evolution_run_id: ID of the evolution run for tracking.
            attempt_number: Which attempt this is (1 for initial, 2+ for regeneration).
            admin_hints: Optional hints from admin for regeneration.

        Returns:
            Tuple of (CodeGenerationResult, validation_passed: bool).
        """
        prompt = CODE_GENERATION_PROMPT.format(
            change_type=law_change.change_type,
            affected_function=law_change.affected_function,
            description=law_change.description,
            old_value=law_change.old_value,
            new_value=law_change.new_value,
            current_code=current_code,
            admin_hints=admin_hints or "None",
        )

        # Call LLM with structured output — store failed attempt on error
        try:
            result = await self.llm.generate_structured(
                messages=[{"role": "user", "content": prompt}],
                response_format=CodeGenerationResult,
                caller="code_generator",
                evolution_run_id=evolution_run_id,
            )
        except LlmCallError as e:
            # Store failed attempt for audit trail, then re-raise
            attempt = GenerationAttempt(
                evolution_run_id=evolution_run_id,
                attempt_number=attempt_number,
                generated_code="",
                validation_passed=False,
                validation_errors={"errors": [str(e)]},
                admin_hints=admin_hints or None,
            )
            self.db.add(attempt)
            await self.db.flush()
            raise

        # Validate the generated code via RestrictedPython
        validation = CodeSandbox.validate(
            code=result.code_content,
            expected_function_name=result.function_name,
        )

        # Store the generation attempt
        attempt = GenerationAttempt(
            evolution_run_id=evolution_run_id,
            attempt_number=attempt_number,
            generated_code=result.code_content,
            validation_passed=validation.passed,
            validation_errors=(
                {"errors": validation.errors, "warnings": validation.warnings}
                if not validation.passed
                else None
            ),
            admin_hints=admin_hints or None,
        )
        self.db.add(attempt)

        # If validation passed, store as DRAFT in AlgorithmRegistry
        if validation.passed:
            draft = AlgorithmRegistry(
                function_name=result.function_name,
                version=result.version,
                code_content=result.code_content,
                status=AlgorithmStatus.DRAFT,
                source_law_hash=None,  # Set later when linked to snapshot
            )
            self.db.add(draft)
            logger.info(
                f"Generated code for {result.function_name} v{result.version} "
                f"(attempt {attempt_number}) — validation PASSED"
            )
        else:
            logger.warning(
                f"Generated code for {result.function_name} v{result.version} "
                f"(attempt {attempt_number}) — validation FAILED: {validation.errors}"
            )

        await self.db.flush()
        return result, validation.passed
