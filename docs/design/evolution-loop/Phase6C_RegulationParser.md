# Phase 6C: Regulation Parser

**Goal:** Use the LLM Gateway to parse crawled NTA page content into structured change descriptions using LiteLLM's structured output with Pydantic models.

**Depends on:** Phase 6A (LLM Gateway) + Phase 6B (NTA Crawler with stored markdown)
**Produces:** `RegulationParser` service, structured `LawChange` and `RegulationAnalysis` Pydantic models, prompt templates, `EvolutionRun` tracking table

---

## Context

After the NTA Crawler (Phase 6B) detects a page change and stores the `fit_markdown`, we need to understand **what changed** in a structured way. Raw markdown from the NTA website is useful but cannot directly drive code generation — we need to extract:

1. **What type of change occurred** (threshold update, new deduction, rate change, etc.)
2. **Which calculation function is affected** (e.g., `calc_income_tax`)
3. **What the old and new values are** (e.g., bracket cap changed from X to Y)
4. **Whether new user input fields are needed** (e.g., a new "fixed tax cut count" field)

This is where the LLM excels — reading natural language tax regulations and extracting structured data.

**Key design decision — LiteLLM Structured Output:**

Instead of asking the LLM for raw text and parsing it manually (fragile), we use LiteLLM's `response_format` parameter with Pydantic models. This gives us:

| Feature | Benefit |
|---------|---------|
| Automatic JSON schema enforcement | LLM provider enforces the schema natively |
| Type-safe responses | Validated via `model_validate_json()` |
| Provider-agnostic | Works with OpenAI, Gemini 2.0+, Claude |
| Client-side validation fallback | `litellm.enable_json_schema_validation = True` |
| No manual parsing | No regex, no text splitting, no error-prone extraction |

Example pattern:

```python
import litellm
from pydantic import BaseModel

class RegulationAnalysis(BaseModel):
    changes: list[LawChange]
    summary: str
    tax_year: int

# Use acompletion() — the async variant — to avoid blocking the event loop
response = await litellm.acompletion(
    model=configured_model,
    messages=[{"role": "user", "content": prompt}],
    response_format=RegulationAnalysis,
)
result = RegulationAnalysis.model_validate_json(
    response.choices[0].message.content
)
```

---

## Tasks

### Task 6C.1: Enums

**File:** `backend/src/domain/enums.py`

```python
class LawChangeType(str, Enum):
    """Types of tax law changes the parser can identify."""
    THRESHOLD_UPDATE = "THRESHOLD_UPDATE"      # A monetary threshold changed
    NEW_DEDUCTION = "NEW_DEDUCTION"            # A new deduction type was introduced
    RATE_CHANGE = "RATE_CHANGE"                # Tax rate or bracket changed
    NEW_FIELD_REQUIRED = "NEW_FIELD_REQUIRED"  # New user input field needed
    BRACKET_CHANGE = "BRACKET_CHANGE"          # Tax bracket boundaries changed
    FORMULA_CHANGE = "FORMULA_CHANGE"          # Calculation formula itself changed
    REGULATION_REMOVED = "REGULATION_REMOVED"  # A deduction or rule was discontinued
```

### Task 6C.2: Pydantic Models for LLM Response

**File:** `backend/src/domain/schemas.py`

These models serve a dual purpose: they are **Pydantic schemas** for API responses AND they are passed to LiteLLM as `response_format` to enforce structured LLM output.

```python
class LawChange(BaseModel):
    """A single identified change in tax regulations.

    Used as LLM response_format for structured output.
    The LawChangeType enum constrains the JSON schema sent to the LLM,
    ensuring it only returns valid change types.
    """
    change_type: LawChangeType = Field(
        description="Type of tax law change identified"
    )
    affected_function: str = Field(
        description="Name of the tax calculation function affected "
        "(e.g., 'calc_income_tax', 'calc_salary_income_deduction')"
    )
    old_value: str = Field(
        description="Previous value or rule (use 'N/A' for new additions)"
    )
    new_value: str = Field(
        description="New value or rule being introduced"
    )
    description: str = Field(
        description="Human-readable description of the change in English"
    )
    confidence_score: float = Field(
        ge=0.0, le=1.0,
        description="LLM confidence in this change identification (0.0 to 1.0)"
    )


class RegulationAnalysis(BaseModel):
    """Structured analysis of NTA regulation changes.

    Returned by the RegulationParser. Used as LLM response_format.
    """
    changes: list[LawChange] = Field(
        description="List of identified law changes"
    )
    summary: str = Field(
        description="Brief summary of all changes found in this regulation update"
    )
    tax_year: int = Field(
        description="The tax year these changes apply to"
    )
    no_changes_detected: bool = Field(
        default=False,
        description="True if the page content changed but no tax rule changes were found "
        "(e.g., only formatting or navigation changes)"
    )
```

### Task 6C.3: Prompt Templates

**File:** `backend/src/domain/prompts.py`

Prompt templates are stored as Python constants — version-controlled and auditable.

```python
"""Prompt templates for LLM interactions.

All prompts are stored here as constants for version control and auditability.
Each prompt includes clear instructions, expected output format, and examples.
"""

REGULATION_PARSE_PROMPT = """You are a Japanese tax regulation expert. Analyze the following
NTA (National Tax Agency) page content and identify any tax law changes compared to the
previous version.

## Current page content (new version):
{new_content}

## Previous page content (if available):
{old_content}

## Currently known calculation functions:
{known_functions}

## Instructions:
1. Compare the new content against the previous content (if provided).
2. Identify ALL tax rule changes: threshold updates, rate changes, new deductions,
   new required fields, bracket changes, formula changes, or removed regulations.
3. For each change, specify which calculation function is affected.
4. If new user input fields are needed (e.g., a new deduction requires a count or amount
   the user must provide), mark it as NEW_FIELD_REQUIRED.
5. Assign a confidence score (0.0-1.0) for each identified change.
6. If the page content changed but NO actual tax rules changed (e.g., only formatting
   or navigation was updated), set no_changes_detected=true.
7. All descriptions must be in English.
8. The tax_year should be the year these changes apply to.

## Known calculation functions (for affected_function field):
- calc_salary_income_deduction: Salary income deduction (給与所得控除)
- calc_basic_deduction: Basic deduction (基礎控除)
- calc_income_tax: Income tax calculation (所得税)
- calc_spouse_deduction: Spouse deduction (配偶者控除)
- calc_dependents_deduction: Dependents deduction (扶養控除)
- calc_social_insurance_deduction: Social insurance deduction (社会保険料控除)
- calc_life_insurance_deduction: Life insurance deduction (生命保険料控除)
- calc_ideco_deduction: iDeCo deduction (小規模企業共済等掛金控除)
- calc_furusato_limit: Furusato Nouzei limit (ふるさと納税上限)

Respond with structured JSON matching the RegulationAnalysis schema.
"""


REGULATION_PARSE_PROMPT_FIRST_SNAPSHOT = """You are a Japanese tax regulation expert.
Analyze the following NTA (National Tax Agency) page content and extract all current
tax rules as structured data.

## Page content:
{content}

## Instructions:
1. Extract ALL tax rules present on this page: thresholds, rates, brackets, deduction
   formulas, eligibility criteria.
2. For each rule, identify which calculation function it corresponds to.
3. This is a BASELINE extraction (no previous version to compare against).
4. Set all change_type values to "THRESHOLD_UPDATE" for existing rules being cataloged.
5. Assign confidence scores based on how clearly the rule is stated on the page.
6. All descriptions must be in English.

Respond with structured JSON matching the RegulationAnalysis schema.
"""
```

### Task 6C.4: Database Model — EvolutionRun

**File:** `backend/src/infrastructure/models.py`

The `EvolutionRun` table tracks each end-to-end evolution pipeline execution:

```python
class EvolutionRun(Base):
    """Tracks an end-to-end evolution pipeline run."""
    __tablename__ = "evolution_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trigger: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # MANUAL / SCHEDULED
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PENDING"
    )  # PENDING, CRAWLING, PARSING, GENERATING, AWAITING_REVIEW,
       # ACCEPTED, MODIFIED, REGENERATING, SKIPPED, DEFERRED, FAILED
    nta_snapshot_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("nta_page_snapshots.id"), nullable=True
    )
    parsed_changes: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # Serialized RegulationAnalysis
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Fields added in Phase 6E for the review workflow:
    # review_decision, rationale, modified_code, regeneration_hints,
    # regeneration_count, max_regenerations
```

### Task 6C.5: Regulation Parser (Infrastructure Layer)

**File:** `backend/src/infrastructure/regulation_parser.py`

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.prompts import (
    REGULATION_PARSE_PROMPT,
    REGULATION_PARSE_PROMPT_FIRST_SNAPSHOT,
)
from src.domain.schemas import RegulationAnalysis
from src.infrastructure.llm_service import LlmService
from src.infrastructure.models import NtaPageSnapshot
from src.logging_config import get_logger

logger = get_logger(__name__)

# List of known calculation functions for the prompt
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
            ValueError: If snapshot not found or has no fit_markdown.
            ValidationError: If LLM response fails Pydantic validation.
        """
        # Get the snapshot
        snapshot = await self.db.get(NtaPageSnapshot, snapshot_id)
        if snapshot is None:
            raise ValueError(f"Snapshot {snapshot_id} not found")
        if not snapshot.fit_markdown:
            raise ValueError(f"Snapshot {snapshot_id} has no fit_markdown")

        # Get the previous snapshot for comparison
        prev_result = await self.db.execute(
            select(NtaPageSnapshot)
            .where(
                NtaPageSnapshot.target_page_id == snapshot.target_page_id,
                NtaPageSnapshot.id < snapshot.id,
                NtaPageSnapshot.status == "SUCCESS",
            )
            .order_by(NtaPageSnapshot.fetched_at.desc())
            .limit(1)
        )
        prev_snapshot = prev_result.scalar_one_or_none()

        # Build the prompt
        if prev_snapshot and prev_snapshot.fit_markdown:
            prompt = REGULATION_PARSE_PROMPT.format(
                new_content=snapshot.fit_markdown,
                old_content=prev_snapshot.fit_markdown,
                known_functions="\n".join(f"- {fn}" for fn in KNOWN_FUNCTIONS),
            )
        else:
            prompt = REGULATION_PARSE_PROMPT_FIRST_SNAPSHOT.format(
                content=snapshot.fit_markdown,
            )

        # Call LLM with structured output
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
```

### Task 6C.6: Alembic Migration

```bash
alembic revision --autogenerate -m "add evolution_runs table"
```

---

## Security

- **Only extracted NTA public text** is sent to the LLM — verified by prompt template structure
- **No user data, PII, or financial information** is ever included in prompts
- LLM responses are **validated against Pydantic schema** automatically; malformed responses are rejected (not silently accepted)
- All LLM calls are **logged to `LlmUsageLog`** (via `LlmService`) with prompt hash, token usage, and cost
- Each parsing operation is linked to an `EvolutionRun` for full audit trail
- Prompt templates are **stored in code** (`domain/prompts.py`) and version-controlled
- **Failed LLM calls** are gracefully handled: retry once, then log error and mark run as FAILED

---

## Test Specification

Per `testing-policy.md`, every task must ship with tests.

### Unit Tests (`tests/domain/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_prompts.py` | `domain/prompts.py` | Prompt templates render correctly with sample inputs, no undefined placeholders |

### Unit Tests (`tests/application/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_regulation_parser.py` | `RegulationParser` | parse() returns validated `RegulationAnalysis` from mocked LLM response, rejects invalid LLM JSON (Pydantic validation error), handles first-snapshot mode (no previous), sets `no_changes_detected=true` when formatting-only change, maps `affected_function` to known function list, `LawChange.change_type` uses `LawChangeType` enum |

### Test Fixtures
- Golden LLM response JSONs in `tests/fixtures/llm_responses/regulation_*.json`.
- Sample NTA markdown in `tests/fixtures/nta_markdown/`.

### Test Conventions
- Mock `LlmService.generate_structured()` — never make real LLM calls.
- Use exact assertions on parsed `LawChange` fields (no `approx()`).

---

## Acceptance Criteria

1. Given NTA `fit_markdown` text, `RegulationParser.parse()` returns a validated `RegulationAnalysis` Pydantic object.
2. Each `LawChange` has a confidence score and maps to an affected calculation function from the known list.
3. LLM responses that fail Pydantic validation are rejected and logged (not silently accepted).
4. When comparing two snapshots, the parser identifies specific changes (thresholds, rates, new fields).
5. When only a first snapshot exists (no previous), the parser extracts baseline rules.
6. If the page changed but no tax rules changed (formatting only), `no_changes_detected` is true.
7. Prompt templates are stored in `domain/prompts.py` and version-controlled.
8. Failed LLM calls are gracefully handled (retry once, then log error and mark run as FAILED).
9. All LLM calls are logged with token usage, cost, and evolution_run_id.
