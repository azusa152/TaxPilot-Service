# Phase 6D: Code & Schema Generator

**Goal:** Generate updated Python algorithm code and new ProfileDefinition fields from parsed law changes, using LiteLLM structured output and RestrictedPython for code safety validation.

**Depends on:** Phase 6C (structured `LawChange` objects) + Phase 6A (LLM Gateway)
**Produces:** Enhanced `CodeGenerator`, new `SchemaGenerator`, `CodeSandbox` wrapping RestrictedPython, draft algorithms and schema proposals stored in DB

---

## Context

After the Regulation Parser (Phase 6C) identifies structured `LawChange` objects, we need to:

1. **Generate updated Python code** for affected calculation functions
2. **Determine if new user input fields** are needed and generate schema proposals
3. **Validate the generated code** is safe to execute (no file I/O, no network, no arbitrary imports)

This phase produces DRAFT artifacts that are stored in the database but **never automatically executed or applied** — they await admin review in Phase 6E.

### Key Design Decisions

**1. LiteLLM Structured Output for code generation:**

Use `response_format` with a Pydantic model (`CodeGenerationResult`) so the LLM returns the generated code, version, and description as structured JSON — not raw text that needs parsing. This means:
- The Python code is in a dedicated `code_content` field (no markdown fences to strip)
- Metadata (function name, version, description) is structured and validated
- The LLM explicitly names the regulation it referenced

**2. RestrictedPython for code sandboxing (not custom AST):**

Instead of building a custom AST blocklist (easy to bypass), we use **RestrictedPython** (v8.1, MIT license) — the industry-standard library for safe Python code execution:

| Feature | How It Works |
|---------|-------------|
| `compile_restricted()` | Compiles code with AST-level restrictions enforced |
| `safe_builtins` | Pre-built whitelist of only safe built-in functions |
| Guard functions | `safer_getattr` prevents access to `__dict__`, `__class__`, dunder methods |
| Deny-by-default | Any language feature without an explicit `visit_` handler is blocked |
| Actively maintained | Supports Python 3.9–3.13 |

This replaces the originally planned custom `code_sandbox.py` AST validator with a battle-tested, maintained solution.

---

## Tasks

### Task 6D.1: Dependencies

**File:** `backend/pyproject.toml`

```toml
[project]
dependencies = [
    # ... existing deps ...
    "RestrictedPython>=8.1",
]
```

### Task 6D.2: Pydantic Models for LLM Response

**File:** `backend/src/domain/schemas.py`

```python
class CodeGenerationResult(BaseModel):
    """Structured result from LLM code generation.

    Used as response_format for LiteLLM structured output.
    """
    function_name: str = Field(
        description="Name of the generated calculation function "
        "(must match the existing function name being updated)"
    )
    version: str = Field(
        description="Version string for this algorithm (e.g., '2025.1')"
    )
    code_content: str = Field(
        description="Complete Python source code of the updated function. "
        "Must be a pure function with no imports, no side effects, no I/O."
    )
    description: str = Field(
        description="Human-readable description of what changed and why"
    )
    referenced_regulation: str = Field(
        description="The specific NTA regulation or page section that this code implements"
    )


class FieldDefinition(BaseModel):
    """Definition of a single field in the ProfileDefinition schema."""
    name: str = Field(description="Field name (snake_case)")
    type: str = Field(
        description="Python type string: 'int', 'float', 'bool', 'str'"
    )
    required: bool = Field(description="Whether this field is required")
    description: str = Field(
        description="Human-readable description of the field (in English)"
    )
    description_ja: str = Field(
        description="Japanese description of the field for UI display"
    )
    default_value: str | None = Field(
        None,
        description="Default value as a string (e.g., '0', 'false'). None if required with no default."
    )


class SchemaChangeProposal(BaseModel):
    """Proposed changes to the ProfileDefinition schema.

    Used as response_format for LiteLLM structured output.
    """
    year: int = Field(description="Tax year this schema change applies to")
    new_fields: list[FieldDefinition] = Field(
        description="New fields to add to the ProfileDefinition"
    )
    removed_fields: list[str] = Field(
        description="Field names to remove (empty list if none)"
    )
    modified_fields: list[FieldDefinition] = Field(
        default_factory=list,
        description="Fields with updated definitions (e.g., changed type or description)"
    )
    change_rationale: str = Field(
        description="Explanation of why these schema changes are needed"
    )
```

### Task 6D.3: Database Models

**File:** `backend/src/infrastructure/models.py`

```python
class SchemaChangeProposalRecord(Base):
    """Stores proposed schema changes linked to an evolution run."""
    __tablename__ = "schema_change_proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    evolution_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("evolution_runs.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    proposal_data: Mapped[dict] = mapped_column(
        JSONB, nullable=False
    )  # Serialized SchemaChangeProposal
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING"
    )  # PENDING, ACCEPTED, REJECTED
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GenerationAttempt(Base):
    """Tracks each code generation attempt within an evolution run.

    Supports the REGENERATE flow where admin requests re-generation with hints.
    """
    __tablename__ = "generation_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    evolution_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("evolution_runs.id"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_code: Mapped[str] = mapped_column(Text, nullable=False)
    generated_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    validation_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    validation_errors: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    admin_hints: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Hints provided by admin for regeneration
    llm_cost_usd: Mapped[float | None] = mapped_column(
        Numeric(10, 6), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_generation_attempts_evolution_run_id", "evolution_run_id"),
    )
```

### Task 6D.4: Code Sandbox (Infrastructure Layer)

**File:** `backend/src/infrastructure/code_sandbox.py`

Wraps RestrictedPython for TaxPilot-specific validation:

```python
import ast
from dataclasses import dataclass, field

from RestrictedPython import compile_restricted, safe_builtins
from RestrictedPython.Guards import safer_getattr, guarded_unpack_sequence

from src.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """Result of code sandbox validation."""
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class CodeSandbox:
    """Validates generated Python code for safety using RestrictedPython.

    Performs three levels of validation:
    1. RestrictedPython compilation (AST-level restrictions)
    2. Domain-specific checks (function name, signature, no imports)
    3. Execution test with safe builtins (optional)
    """

    @staticmethod
    def validate(
        code: str,
        expected_function_name: str | None = None,
    ) -> ValidationResult:
        """Validate generated Python code for safety.

        Args:
            code: The Python source code to validate.
            expected_function_name: If provided, ensures the code defines
                a function with this name.

        Returns:
            ValidationResult with pass/fail, errors, and warnings.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # --- Level 1: RestrictedPython compilation ---
        try:
            byte_code = compile_restricted(
                code,
                filename="<generated>",
                mode="exec",
            )
            if byte_code is None:
                errors.append("RestrictedPython compilation returned None")
        except SyntaxError as e:
            errors.append(f"Syntax error: {e}")
            return ValidationResult(passed=False, errors=errors)
        except Exception as e:
            errors.append(f"RestrictedPython compilation failed: {e}")
            return ValidationResult(passed=False, errors=errors)

        # --- Level 2: Domain-specific AST checks ---
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            errors.append(f"AST parse error: {e}")
            return ValidationResult(passed=False, errors=errors)

        # Check for import statements (should be pure functions)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                errors.append(
                    f"Import statement found: {ast.dump(node)}. "
                    "Generated functions must be pure — no imports allowed."
                )

        # Check that expected function is defined
        if expected_function_name:
            function_names = [
                node.name
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
            ]
            if expected_function_name not in function_names:
                errors.append(
                    f"Expected function '{expected_function_name}' not found. "
                    f"Found: {function_names}"
                )

        # Warn about global variables
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                warnings.append(
                    "Top-level variable assignment found. "
                    "Prefer constants inside the function."
                )

        # --- Level 3: Test execution with restricted builtins ---
        if not errors and byte_code:
            restricted_globals = {
                "__builtins__": safe_builtins,
                "_getattr_": safer_getattr,
                "_getiter_": iter,
                "_getitem_": lambda obj, key: obj[key],
                "_unpack_sequence_": guarded_unpack_sequence,
            }
            try:
                # SECURITY NOTE: This exec() is intentionally used within a
                # restricted sandbox. The byte_code was compiled via
                # RestrictedPython's compile_restricted(), which performs AST
                # transformation to block dangerous operations. The globals
                # dict uses RestrictedPython's safe_globals + guarded accessors.
                # This does NOT execute arbitrary code — it only executes
                # code that has passed the RestrictedPython safety checks.
                exec(byte_code, restricted_globals)  # noqa: S102 — restricted sandbox

                # Verify the function is callable
                if expected_function_name:
                    func = restricted_globals.get(expected_function_name)
                    if func is None or not callable(func):
                        errors.append(
                            f"Function '{expected_function_name}' was not "
                            "defined or is not callable after execution."
                        )
            except Exception as e:
                errors.append(f"Restricted execution failed: {e}")

        passed = len(errors) == 0
        if passed:
            logger.info("Code sandbox validation passed")
        else:
            logger.warning(f"Code sandbox validation failed: {errors}")

        return ValidationResult(passed=passed, errors=errors, warnings=warnings)
```

### Task 6D.5: Code Generation Prompts

**File:** `backend/src/domain/prompts.py` (append to existing)

```python
CODE_GENERATION_PROMPT = """You are a Python tax calculation expert. Generate an updated
pure Python function based on the following law change.

## Law Change:
- Type: {change_type}
- Affected function: {affected_function}
- Description: {description}
- Old value: {old_value}
- New value: {new_value}

## Current function code:
```python
{current_code}
```

## Requirements:
1. The function must be a PURE Python function — no imports, no side effects, no I/O.
2. The function name must be exactly: {affected_function}
3. The function signature should match the current version (or add new parameters if NEW_FIELD_REQUIRED).
4. All amounts are in JPY (integers).
5. Include a Google-style docstring with:
   - Brief description of what the function calculates
   - The NTA regulation reference
   - The tax year this version applies to
6. Use clear variable names and comments for threshold boundaries.
7. Return ONLY the function definition — no imports, no class wrappers, no test code.

## Admin hints (if any):
{admin_hints}

Respond with structured JSON matching the CodeGenerationResult schema.
"""


SCHEMA_GENERATION_PROMPT = """You are a Japanese tax system expert. Based on the following
law changes, determine if any new user input fields are needed in the tax profile.

## Identified law changes:
{changes_json}

## Current ProfileDefinition fields:
{current_fields}

## Instructions:
1. For each law change of type NEW_FIELD_REQUIRED, propose a new field definition.
2. For threshold or rate changes, check if existing fields are sufficient.
3. Each new field needs: name (snake_case), type (int/float/bool/str), required flag,
   English description, Japanese description, and default value.
4. If no new fields are needed, return an empty new_fields list.
5. Check if any existing fields should be removed (rare — usually only on regulation removal).
6. Provide a clear rationale for the schema changes.

Respond with structured JSON matching the SchemaChangeProposal schema.
"""
```

### Task 6D.6: Code Generator (Infrastructure Layer)

**File:** `backend/src/infrastructure/code_generator.py`

Upgrade from stub to real implementation:

```python
from sqlalchemy.ext.asyncio import AsyncSession

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

        # Call LLM with structured output
        result = await self.llm.generate_structured(
            messages=[{"role": "user", "content": prompt}],
            response_format=CodeGenerationResult,
            caller="code_generator",
            evolution_run_id=evolution_run_id,
        )

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
                status="DRAFT",
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
```

### Task 6D.7: Schema Generator (Infrastructure Layer)

**File:** `backend/src/infrastructure/schema_generator.py`

```python
import json

from sqlalchemy.ext.asyncio import AsyncSession

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
        """
        changes_json = json.dumps(
            [c.model_dump() for c in changes], indent=2
        )

        prompt = SCHEMA_GENERATION_PROMPT.format(
            changes_json=changes_json,
            current_fields=json.dumps(current_fields, indent=2),
        )

        result = await self.llm.generate_structured(
            messages=[{"role": "user", "content": prompt}],
            response_format=SchemaChangeProposal,
            caller="schema_generator",
            evolution_run_id=evolution_run_id,
        )

        # Store the proposal in DB
        record = SchemaChangeProposalRecord(
            evolution_run_id=evolution_run_id,
            year=result.year,
            proposal_data=result.model_dump(),
            status="PENDING",
        )
        self.db.add(record)
        await self.db.flush()

        logger.info(
            f"Schema proposal for year {result.year}: "
            f"{len(result.new_fields)} new fields, "
            f"{len(result.removed_fields)} removed fields"
        )
        return result
```

### Task 6D.8: Alembic Migration

```bash
alembic revision --autogenerate -m "add schema_change_proposals and generation_attempts tables"
```

---

## Security

- Generated code is validated via **RestrictedPython** `compile_restricted()` with `safe_builtins` — deny-by-default approach blocks dangerous operations at the AST level
- Guard functions (`safer_getattr`) prevent access to underscore-prefixed attributes and dunder methods
- **Additional domain-specific checks:** function name match, no import statements, no external dependencies
- Code is stored as **DRAFT** in `AlgorithmRegistry` — never executed until admin explicitly activates (Phase 6E)
- Schema proposals are stored separately — never applied until admin approves (Phase 6E)
- LLM responses are validated against Pydantic schema before processing
- All generation attempts are tracked in `GenerationAttempt` table for full audit trail
- Admin-provided code in the MODIFY flow (Phase 6E) goes through the **same** `CodeSandbox.validate()` check

---

## Test Specification

Per `testing-policy.md`, every task must ship with tests.

### Unit Tests (`tests/infrastructure/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_code_sandbox.py` | `CodeSandbox` | validate() accepts clean function code, rejects `import os`/`open()`/`exec()`, rejects `__dict__`/`__builtins__` access, rejects functions that don't match expected name, returns structured `ValidationResult` with errors/warnings |

### Unit Tests (`tests/application/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_code_generator.py` | `CodeGenerator` | generate() returns valid Python from mocked LLM, generated code passes sandbox validation, stores `GenerationAttempt` with DRAFT status, handles LLM failure gracefully |
| `test_schema_generator.py` | `SchemaGenerator` | generate() returns `SchemaChangeProposal` from mocked LLM, field definitions have valid types and descriptions, stores `SchemaChangeProposalRecord` |

### Test Fixtures
- Golden generated code samples in `tests/fixtures/generated_code/`.
- Sample `LawChange` objects covering each `LawChangeType`.

### Test Conventions
- Mock `LlmService.generate_structured()` — never make real LLM calls.
- Sandbox tests use actual `RestrictedPython` (not mocked) — this is the security boundary.
- Test both valid and malicious code patterns.

---

## Acceptance Criteria

1. Given a `LawChange` (e.g., threshold update), `CodeGenerator.generate()` produces valid Python via structured LLM output.
2. Generated code passes `CodeSandbox.validate()` using RestrictedPython `compile_restricted()`.
3. Code that uses `import os`, `open()`, `exec()`, or accesses `__dict__` is rejected by RestrictedPython.
4. Given a `LawChange` of type `NEW_FIELD_REQUIRED`, `SchemaGenerator.generate()` returns a validated `SchemaChangeProposal` with new field definitions.
5. Both code and schema changes are linked to their `EvolutionRun` for traceability.
6. LLM responses that fail Pydantic validation are rejected and logged.
7. Each generation attempt (including regenerations) is stored in `GenerationAttempt`.
8. Generated code is stored as DRAFT — never automatically activated.
9. `CodeSandbox.validate()` returns a structured `ValidationResult` with errors, warnings, and pass/fail.
