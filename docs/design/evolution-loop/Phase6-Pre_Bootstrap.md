# Phase 6-Pre: Bootstrap & Verification

**Goal:** Solve the cold start problem. Bootstrap the system from hardcoded formulas to a fully tracked, registry-based architecture. Crawl NTA pages for baselines. Use LLM to verify existing formulas match actual NTA regulations.

**Depends on:** Phase 6A (LLM Gateway) + Phase 6B (NTA Crawler) + Phase 6C (Regulation Parser) + Phase 6D (Code Sandbox)
**Produces:** Populated AlgorithmRegistry with `source_law_hash`, baseline NTA snapshots with markdown, LLM verification report, migrated `tax_service.py`

---

## Context

### The Cold Start Problem

Currently, the source of truth for tax formulas is `backend/src/domain/tax_calculations.py` — 9 hardcoded pure functions for the 2024 tax year. These are directly imported by `tax_service.py`. The `AlgorithmRegistry` table exists but is **empty and unused for runtime calculations**.

The Evolution Loop cannot detect changes or generate updates without:

1. **Knowing what the current formulas are** (registered in `AlgorithmRegistry`)
2. **Having baseline NTA snapshots** to compare future changes against
3. **Linking each formula to its NTA regulation source** via `source_law_hash`

### What Bootstrap Does

Bootstrap is a **one-time initialization** (idempotent, safe to re-run) that bridges Phases 1–5 (hardcoded) to Phase 6 (dynamic). It runs 4 steps in order:

```
Step 1: Baseline NTA Crawl
    ↓
Step 2: Seed AlgorithmRegistry from tax_calculations.py
    ↓
Step 3: LLM Verification (validate formulas against NTA text)
    ↓
Step 4: Migrate tax_service.py to use AlgorithmLoader
```

---

## Tasks

### Task 6Pre.1: NTA Target Pages Configuration

Before bootstrap can run, we need to configure which NTA pages to crawl. These mappings link NTA pages to the functions they source:

| NTA Page | URL | Functions It Sources |
|----------|-----|---------------------|
| Income tax rates | `https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2260.htm` | `calc_income_tax`, `calc_basic_deduction` |
| Salary deduction | `https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1410.htm` | `calc_salary_income_deduction` |
| Spouse deduction | `https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1191.htm` | `calc_spouse_deduction` |
| Dependents deduction | `https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1180.htm` | `calc_dependents_deduction` |
| Social insurance | `https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1130.htm` | `calc_social_insurance_deduction` |
| Life insurance | `https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1140.htm` | `calc_life_insurance_deduction` |
| iDeCo / small enterprise | `https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1135.htm` | `calc_ideco_deduction` |
| Furusato Nouzei | (soumu.go.jp reference) | `calc_furusato_limit` |

*(Exact URLs to be confirmed during implementation; these are the primary NTA TaxAnswer pages)*

The bootstrap script seeds these as `NtaTargetPage` records if they don't already exist.

### Task 6Pre.2: Enums

**File:** `backend/src/domain/enums.py`

```python
class VerificationStatus(str, Enum):
    """Result of verifying a formula against NTA text."""
    MATCH = "MATCH"              # Formula matches NTA text
    MISMATCH = "MISMATCH"        # Formula does NOT match NTA text
    PARTIAL_MATCH = "PARTIAL"    # Some aspects match, some differ
```

### Task 6Pre.3: Database Models

**File:** `backend/src/infrastructure/models.py`

```python
class BootstrapVerificationReport(Base):
    """Stores LLM verification results for each formula against NTA text."""
    __tablename__ = "bootstrap_verification_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    function_name: Mapped[str] = mapped_column(String(100), nullable=False)
    nta_page_name: Mapped[str] = mapped_column(String(100), nullable=False)
    nta_snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("nta_page_snapshots.id"), nullable=False
    )
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # MATCH / MISMATCH / PARTIAL
    details: Mapped[dict] = mapped_column(
        JSONB, nullable=False
    )  # LLM-extracted rules vs hardcoded logic
    confidence_score: Mapped[float] = mapped_column(
        Numeric(3, 2), nullable=False
    )  # 0.00 to 1.00
    llm_extracted_rules: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Human-readable summary of what the LLM extracted
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

### Task 6Pre.4: Pydantic Schemas

**File:** `backend/src/domain/schemas.py`

```python
class VerificationResult(BaseModel):
    """Result of verifying a single formula against NTA text.

    Used as LLM response_format for structured verification output.
    """
    function_name: str = Field(
        description="Name of the tax calculation function being verified"
    )
    status: VerificationStatus = Field(
        description="Verification result: MATCH, MISMATCH, or PARTIAL. "
        "The enum constrains the LLM's JSON schema to only valid values."
    )
    extracted_thresholds: list[dict] = Field(
        description="Tax thresholds/rates extracted from the NTA text by the LLM. "
        "Each entry: {bracket: str, threshold: int, rate_or_amount: str}"
    )
    hardcoded_comparison: str = Field(
        description="Line-by-line comparison of LLM-extracted rules vs hardcoded logic"
    )
    discrepancies: list[str] = Field(
        description="List of specific discrepancies found (empty if MATCH)"
    )
    confidence_score: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in the verification result"
    )
    summary: str = Field(
        description="Brief summary of the verification in English"
    )


class BootstrapReport(BaseModel):
    """Overall bootstrap verification report."""
    total_functions: int = Field(description="Total functions verified")
    matched: int = Field(description="Number of functions that match NTA text")
    mismatched: int = Field(description="Number of functions with mismatches")
    partial: int = Field(description="Number of partial matches")
    results: list[VerificationResult] = Field(
        description="Per-function verification results"
    )
    bootstrap_completed_at: datetime
```

### Task 6Pre.5: Verification Prompt

**File:** `backend/src/domain/prompts.py` (append to existing)

```python
VERIFICATION_PROMPT = """You are a Japanese tax regulation expert. Verify whether the
following Python tax calculation function correctly implements the rules described in the
NTA page content.

## NTA Page Content (authoritative source):
{nta_content}

## Python function to verify:
```python
{function_code}
```

## Function name: {function_name}

## Instructions:
1. Read the NTA page content carefully and extract ALL tax thresholds, rates, brackets,
   and calculation rules.
2. Compare each extracted rule against the Python function's logic.
3. For bracket-based functions, verify EVERY threshold boundary and corresponding rate/amount.
4. Report the verification status:
   - MATCH: All rules in the function match the NTA text
   - MISMATCH: One or more rules differ between the function and NTA text
   - PARTIAL: Some rules match, but some cannot be verified (e.g., NTA text is ambiguous)
5. List specific discrepancies if any (e.g., "NTA states bracket cap of 1,950,000 for salary
   deduction — matches line 31 of the function" or "NTA states rate of 10% for bracket 2,
   but function uses 0.12").
6. Assign a confidence score (0.0-1.0) for the overall verification.

Respond with structured JSON matching the VerificationResult schema.
"""
```

### Task 6Pre.6: Bootstrap Script (Infrastructure Layer)

**File:** `backend/src/infrastructure/bootstrap.py`

Orchestrates all 4 bootstrap steps as an **idempotent** script:

```python
import inspect
import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain import tax_calculations
from src.domain.prompts import VERIFICATION_PROMPT
from src.domain.schemas import VerificationResult
from src.infrastructure.llm_service import LlmService
from src.infrastructure.models import (
    AlgorithmRegistry,
    BootstrapVerificationReport,
    NtaPageSnapshot,
    NtaTargetPage,
)
from src.infrastructure.nta_monitor import NtaMonitor
from src.logging_config import get_logger

logger = get_logger(__name__)

# Mapping of NTA pages to the functions they source
NTA_PAGE_FUNCTION_MAP = {
    "income_tax_rates": ["calc_income_tax", "calc_basic_deduction"],
    "salary_deduction": ["calc_salary_income_deduction"],
    "spouse_deduction": ["calc_spouse_deduction"],
    "dependents_deduction": ["calc_dependents_deduction"],
    "social_insurance": ["calc_social_insurance_deduction"],
    "life_insurance": ["calc_life_insurance_deduction"],
    "ideco_deduction": ["calc_ideco_deduction"],
    "furusato_nouzei": ["calc_furusato_limit"],
}

# All functions to register from tax_calculations.py.
# NOTE: calc_taxable_income is EXCLUDED because it is a pure orchestration
# function that calls the other registered functions. It does not contain
# tax law logic itself — it aggregates results. If the orchestration logic
# changes, it should be updated manually in tax_service.py, not via the
# Evolution Loop's code generation pipeline.
FUNCTIONS_TO_REGISTER = [
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

# NTA target pages to seed (name, URL, description)
NTA_TARGET_PAGES = [
    (
        "income_tax_rates",
        "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2260.htm",
        "Income tax rates and basic deduction (所得税の税率, 基礎控除)",
    ),
    (
        "salary_deduction",
        "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1410.htm",
        "Salary income deduction (給与所得控除)",
    ),
    (
        "spouse_deduction",
        "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1191.htm",
        "Spouse deduction (配偶者控除)",
    ),
    (
        "dependents_deduction",
        "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1180.htm",
        "Dependents deduction (扶養控除)",
    ),
    (
        "social_insurance",
        "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1130.htm",
        "Social insurance deduction (社会保険料控除)",
    ),
    (
        "life_insurance",
        "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1140.htm",
        "Life insurance deduction (生命保険料控除)",
    ),
    (
        "ideco_deduction",
        "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1135.htm",
        "iDeCo / small enterprise mutual aid (小規模企業共済等掛金控除)",
    ),
    (
        "furusato_nouzei",
        "https://www.soumu.go.jp/main_sosiki/jichi_zeisei/czaisei/czaisei_seido/furusato/mechanism/deduction.html",
        "Furusato Nouzei deduction mechanism (ふるさと納税)",
    ),
]


class BootstrapRunner:
    """Orchestrates the cold start bootstrap process.

    All steps are idempotent — safe to run multiple times.
    """

    def __init__(self, db: AsyncSession, llm_service: LlmService | None = None):
        self.db = db
        self.llm = llm_service  # None = skip LLM verification step

    async def run(self, skip_verification: bool = False) -> dict:
        """Execute all bootstrap steps.

        Args:
            skip_verification: If True, skip Step 3 (LLM verification).
                Useful for initial setup when LLM is not yet configured.

        Returns:
            Summary dict with results from each step.
        """
        summary = {}

        # Step 1: Seed NTA target pages + baseline crawl
        logger.info("Bootstrap Step 1: Baseline NTA crawl")
        summary["step1_crawl"] = await self._step1_baseline_crawl()

        # Step 2: Seed AlgorithmRegistry
        logger.info("Bootstrap Step 2: Seed AlgorithmRegistry")
        summary["step2_seed"] = await self._step2_seed_registry()

        # Step 3: LLM verification (optional)
        if not skip_verification and self.llm:
            logger.info("Bootstrap Step 3: LLM verification")
            summary["step3_verify"] = await self._step3_verify()
        else:
            logger.info("Bootstrap Step 3: Skipped (no LLM configured or skip requested)")
            summary["step3_verify"] = "skipped"

        # Step 4 is a code change (migrate tax_service.py) — done manually
        summary["step4_migrate"] = (
            "Manual: migrate tax_service.py to use AlgorithmLoader"
        )

        await self.db.commit()
        logger.info(f"Bootstrap complete: {summary}")
        return summary

    async def _step1_baseline_crawl(self) -> dict:
        """Seed NTA target pages and perform baseline crawl."""
        pages_seeded = 0
        pages_crawled = 0

        for name, url, description in NTA_TARGET_PAGES:
            # Check if target page already exists
            result = await self.db.execute(
                select(NtaTargetPage).where(NtaTargetPage.name == name)
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                page = NtaTargetPage(
                    name=name, url=url, description=description, is_active=True
                )
                self.db.add(page)
                pages_seeded += 1

        await self.db.flush()

        # Crawl all pages
        monitor = NtaMonitor(self.db)
        changes = await monitor.check_for_changes(trigger="BOOTSTRAP")
        pages_crawled = len(changes)  # All pages will be "changed" on first crawl

        return {
            "pages_seeded": pages_seeded,
            "pages_crawled": pages_crawled,
        }

    async def _step2_seed_registry(self) -> dict:
        """Register existing hardcoded functions in AlgorithmRegistry."""
        registered = 0
        skipped = 0

        for func_name in FUNCTIONS_TO_REGISTER:
            # Check if already registered
            result = await self.db.execute(
                select(AlgorithmRegistry).where(
                    AlgorithmRegistry.function_name == func_name,
                    AlgorithmRegistry.status == "ACTIVE",
                )
            )
            if result.scalar_one_or_none():
                skipped += 1
                continue

            # Get the source code using inspect
            func = getattr(tax_calculations, func_name, None)
            if func is None:
                logger.warning(f"Function {func_name} not found in tax_calculations.py")
                continue

            source_code = inspect.getsource(func)

            # Compute source_law_hash from the corresponding NTA snapshot
            source_law_hash = await self._get_source_law_hash(func_name)

            algo = AlgorithmRegistry(
                function_name=func_name,
                version="2024.1",
                code_content=source_code,
                status="ACTIVE",
                source_law_hash=source_law_hash,
            )
            self.db.add(algo)
            registered += 1

        await self.db.flush()
        return {"registered": registered, "skipped": skipped}

    async def _get_source_law_hash(self, func_name: str) -> str | None:
        """Get the content_hash of the NTA snapshot that sources this function."""
        for page_name, functions in NTA_PAGE_FUNCTION_MAP.items():
            if func_name in functions:
                # Get the latest snapshot for this page
                result = await self.db.execute(
                    select(NtaPageSnapshot)
                    .join(NtaTargetPage)
                    .where(
                        NtaTargetPage.name == page_name,
                        NtaPageSnapshot.status == "SUCCESS",
                    )
                    .order_by(NtaPageSnapshot.fetched_at.desc())
                    .limit(1)
                )
                snapshot = result.scalar_one_or_none()
                if snapshot:
                    return snapshot.content_hash
        return None

    async def _step3_verify(self) -> dict:
        """Verify existing formulas against NTA text using LLM."""
        results = []

        for page_name, func_names in NTA_PAGE_FUNCTION_MAP.items():
            # Get the latest snapshot
            result = await self.db.execute(
                select(NtaPageSnapshot)
                .join(NtaTargetPage)
                .where(
                    NtaTargetPage.name == page_name,
                    NtaPageSnapshot.status == "SUCCESS",
                )
                .order_by(NtaPageSnapshot.fetched_at.desc())
                .limit(1)
            )
            snapshot = result.scalar_one_or_none()
            if not snapshot or not snapshot.fit_markdown:
                logger.warning(f"No snapshot available for {page_name}, skipping verification")
                continue

            for func_name in func_names:
                func = getattr(tax_calculations, func_name, None)
                if func is None:
                    continue

                source_code = inspect.getsource(func)

                # Ask LLM to verify
                prompt = VERIFICATION_PROMPT.format(
                    nta_content=snapshot.fit_markdown,
                    function_code=source_code,
                    function_name=func_name,
                )

                verification = await self.llm.generate_structured(
                    messages=[{"role": "user", "content": prompt}],
                    response_format=VerificationResult,
                    caller="bootstrap_verification",
                )

                # Store the report
                report = BootstrapVerificationReport(
                    function_name=func_name,
                    nta_page_name=page_name,
                    nta_snapshot_id=snapshot.id,
                    verification_status=verification.status,
                    details={
                        "extracted_thresholds": verification.extracted_thresholds,
                        "hardcoded_comparison": verification.hardcoded_comparison,
                        "discrepancies": verification.discrepancies,
                    },
                    confidence_score=verification.confidence_score,
                    llm_extracted_rules=verification.summary,
                )
                self.db.add(report)
                results.append(verification)

        await self.db.flush()

        matched = sum(1 for r in results if r.status == "MATCH")
        mismatched = sum(1 for r in results if r.status == "MISMATCH")
        partial = sum(1 for r in results if r.status == "PARTIAL")

        return {
            "total": len(results),
            "matched": matched,
            "mismatched": mismatched,
            "partial": partial,
        }
```

### Task 6Pre.7: Migrate `tax_service.py` to Use AlgorithmLoader

**File:** `backend/src/application/tax_service.py`

Replace direct imports from `tax_calculations.py` with `AlgorithmLoader.get_function()` calls, using the hardcoded functions as fallback:

```python
from src.domain import tax_calculations  # Fallback
from src.infrastructure.algorithm_loader import AlgorithmLoader


def _get_calc_function(name: str) -> callable:
    """Load a calculation function from AlgorithmLoader with fallback.

    Tries the dynamic registry first. If not found (e.g., registry is empty
    or loading fails), falls back to the hardcoded functions in tax_calculations.py.
    """
    try:
        return AlgorithmLoader.get_function(name)
    except Exception:
        # Fallback to hardcoded functions
        func = getattr(tax_calculations, name, None)
        if func is None:
            raise ValueError(f"Calculation function '{name}' not found in registry or fallback")
        return func


async def calculate_tax(db: AsyncSession, user_id: str, year: int) -> TaxCalculationResult:
    """Run full tax calculation for a user and year.

    Uses AlgorithmLoader for dynamic function loading with tax_calculations.py fallback.
    """
    # ... existing profile/entries fetching logic ...

    # Load functions dynamically
    calc_salary_ded = _get_calc_function("calc_salary_income_deduction")
    calc_basic = _get_calc_function("calc_basic_deduction")
    calc_social = _get_calc_function("calc_social_insurance_deduction")
    calc_life = _get_calc_function("calc_life_insurance_deduction")
    calc_spouse = _get_calc_function("calc_spouse_deduction")
    calc_deps = _get_calc_function("calc_dependents_deduction")
    calc_ideco = _get_calc_function("calc_ideco_deduction")
    calc_tax = _get_calc_function("calc_income_tax")

    # Run calculations using loaded functions
    salary_ded = calc_salary_ded(gross_salary)
    total_income = gross_salary - salary_ded
    basic_ded = calc_basic(total_income)
    # ... rest of calculation logic using loaded functions ...
```

**Important:** `tax_calculations.py` remains **unchanged** — it is preserved as the fallback and reference implementation.

### Task 6Pre.8: Streamlit Admin Page — Bootstrap Status

**File:** `admin/app.py` (new section)

The "Bootstrap Status" section shows:

1. **Bootstrap Status:**
   - Whether bootstrap has been run (check if `AlgorithmRegistry` has ACTIVE entries)
   - Timestamp of last bootstrap run
   - "Run Bootstrap" button (with confirmation dialog)
   - "Re-run Verification Only" button (useful after LLM prompt improvements)

2. **Verification Report:**
   - Table of all functions with their verification status (MATCH / MISMATCH / PARTIAL)
   - Color-coded rows: green for MATCH, red for MISMATCH, yellow for PARTIAL
   - Click to expand and see detailed comparison (LLM-extracted rules vs hardcoded logic)
   - Confidence scores per function
   - Discrepancy details for MISMATCH/PARTIAL results

3. **Registry Status:**
   - Table of all registered algorithms (function_name, version, status, source_law_hash)
   - Indicates which functions are using dynamic registry vs fallback

### Task 6Pre.9: Alembic Migration

```bash
alembic revision --autogenerate -m "add bootstrap_verification_reports table"
```

---

## Security

- Bootstrap script is **idempotent** (safe to re-run; skips already-registered algorithms)
- **Only public NTA text** is sent to LLM for verification
- Verification report is stored but **does not auto-modify any formulas** (read-only analysis)
- Admin must manually review mismatches before taking action
- **Fallback preserved:** `tax_calculations.py` is unchanged — if `AlgorithmLoader` fails, `tax_service` uses hardcoded functions
- Bootstrap execution is logged to audit trail

---

## Test Specification

Per `testing-policy.md`, every task must ship with tests.

### Unit Tests (`tests/application/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_bootstrap_runner.py` | `BootstrapRunner` | step1 stores baseline snapshots (mock Crawl4AI), step2 registers all 9 known functions with source code, step2 is idempotent (no duplicates on re-run), step3 returns `VerificationResult` with `VerificationStatus` enum values (MATCH/MISMATCH/PARTIAL), full run() orchestrates all steps in order |

### Unit Tests (`tests/infrastructure/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_algorithm_loader.py` | `AlgorithmLoader` | loads function from registry when ACTIVE entry exists, falls back to `tax_calculations.py` when registry is empty, rejects code that fails sandbox validation |

### Integration Tests (`tests/api/`)

| Test File | Scope | Key Cases |
|-----------|-------|-----------|
| `test_bootstrap_routes.py` | API endpoints | `POST /admin/bootstrap/run` triggers full bootstrap, `GET /admin/bootstrap/report` returns verification results |

### Test Conventions
- Mock `Crawl4AI`, mock `LlmService` — never make real external calls.
- Verify registry counts with exact assertions.
- Test that `tax_service.py` produces identical results before and after AlgorithmLoader migration (regression test).

---

## Acceptance Criteria

1. Running `BootstrapRunner.run()` crawls all target NTA pages and stores baseline snapshots with markdown.
2. All 9 existing functions from `tax_calculations.py` are registered as ACTIVE in `AlgorithmRegistry` with `source_law_hash`.
3. LLM verification report is generated and stored, showing match status for each formula.
4. `tax_service.py` loads functions from `AlgorithmLoader` and falls back to `tax_calculations.py` if registry is empty.
5. Admin can view the verification report in the Streamlit dashboard.
6. Bootstrap is idempotent — running it again does not create duplicates.
7. **Existing API behavior is unchanged** — same calculation results before and after migration.
8. Admin can re-run verification independently (e.g., after improving prompts).
