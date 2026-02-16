"""Bootstrap runner — cold start initialization for the Evolution Loop.

Orchestrates 4 steps:
1. Seed NTA target pages + baseline crawl
2. Seed AlgorithmRegistry from tax_calculations.py
3. LLM verification (validate formulas against NTA text)
4. Migrate tax_service.py to use AlgorithmLoader (manual code change)

All steps are idempotent — safe to run multiple times.
"""

import inspect

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain import tax_calculations
from src.domain.enums import (
    AlgorithmStatus,
    CrawlerRunTrigger,
    SnapshotStatus,
    VerificationStatus,
)
from src.domain.exceptions import LlmCallError
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

# Mapping of NTA page names to the functions they source.
NTA_PAGE_FUNCTION_MAP: dict[str, list[str]] = {
    "income_tax_rates": ["calc_income_tax", "calc_basic_deduction"],
    "salary_deduction": ["calc_salary_income_deduction"],
    "spouse_deduction": ["calc_spouse_deduction"],
    "dependents_deduction": ["calc_dependents_deduction"],
    "social_insurance": ["calc_social_insurance_deduction"],
    "life_insurance": ["calc_life_insurance_deduction"],
    "ideco_deduction": ["calc_ideco_deduction"],
    "furusato_nouzei": ["calc_furusato_limit"],
}

# Functions to register from tax_calculations.py.
# NOTE: calc_taxable_income is EXCLUDED — it is a pure orchestration function
# that calls the other registered functions. It does not contain tax law logic
# itself and should be updated manually, not via the Evolution Loop.
FUNCTIONS_TO_REGISTER: list[str] = [
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

# NTA target pages to seed: (name, url, description, source_type)
NTA_TARGET_PAGES: list[tuple[str, str, str, str]] = [
    (
        "income_tax_rates",
        "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2260.htm",
        "Income tax rates and basic deduction (所得税の税率, 基礎控除)",
        "NTA_TAX_ANSWER",
    ),
    (
        "salary_deduction",
        "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1410.htm",
        "Salary income deduction (給与所得控除)",
        "NTA_TAX_ANSWER",
    ),
    (
        "spouse_deduction",
        "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1191.htm",
        "Spouse deduction (配偶者控除)",
        "NTA_TAX_ANSWER",
    ),
    (
        "dependents_deduction",
        "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1180.htm",
        "Dependents deduction (扶養控除)",
        "NTA_TAX_ANSWER",
    ),
    (
        "social_insurance",
        "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1130.htm",
        "Social insurance deduction (社会保険料控除)",
        "NTA_TAX_ANSWER",
    ),
    (
        "life_insurance",
        "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1140.htm",
        "Life insurance deduction (生命保険料控除)",
        "NTA_TAX_ANSWER",
    ),
    (
        "ideco_deduction",
        "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1135.htm",
        "iDeCo / small enterprise mutual aid (小規模企業共済等掛金控除)",
        "NTA_TAX_ANSWER",
    ),
    (
        "furusato_nouzei",
        "https://www.soumu.go.jp/main_sosiki/jichi_zeisei/czaisei/czaisei_seido/furusato/mechanism/deduction.html",
        "Furusato Nouzei deduction mechanism (ふるさと納税)",
        "NTA_TAX_ANSWER",
    ),
    (
        "basic_deduction",
        "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1199.htm",
        "Basic deduction details (基礎控除)",
        "NTA_TAX_ANSWER",
    ),
    (
        "furusato_nta",
        "https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1155.htm",
        "Furusato Nouzei on NTA (ふるさと納税 - 国税庁)",
        "NTA_TAX_ANSWER",
    ),
    # MOF Tax Reform (Layer 2)
    (
        "mof_tax_reform_outline",
        "https://www.mof.go.jp/tax_policy/tax_reform/outline/index.html",
        "MOF Tax Reform outline page (財務省 税制改正)",
        "MOF_TAX_REFORM",
    ),
    # e-Gov Laws (Layer 3)
    (
        "egov_income_tax_law",
        "egov://340AC0000000033",
        "Income Tax Act from e-Gov (所得税法)",
        "EGOV_LAW",
    ),
    (
        "egov_local_tax_law",
        "egov://325AC0000000226",
        "Local Tax Act from e-Gov (地方税法)",
        "EGOV_LAW",
    ),
]


class BootstrapRunner:
    """Orchestrates the cold start bootstrap process.

    All steps are idempotent — safe to run multiple times.
    """

    def __init__(self, db: AsyncSession, llm_service: LlmService | None = None):
        self.db = db
        self.llm = llm_service  # None = skip LLM verification step

    async def run(self, skip_crawl: bool = False, skip_verification: bool = False) -> dict:
        """Execute all bootstrap steps.

        Args:
            skip_crawl: If True, skip Step 1 (baseline NTA crawl).
                Useful in test environments where crawling is not possible.
            skip_verification: If True, skip Step 3 (LLM verification).
                Useful for initial setup when LLM is not yet configured.

        Returns:
            Summary dict with results from each step.
        """
        summary: dict = {}

        # Step 1: Seed NTA target pages + baseline crawl
        logger.info("Bootstrap Step 1: Seed NTA target pages + baseline crawl")
        summary["step1_crawl"] = await self._step1_baseline_crawl(skip_crawl=skip_crawl)

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

        # Step 4 is a code change (migrate tax_service.py) — done in Task 6Pre.7
        summary["step4_migrate"] = "Manual: migrate tax_service.py to use AlgorithmLoader"

        await self.db.commit()
        logger.info(f"Bootstrap complete: {summary}")
        return summary

    async def _step1_baseline_crawl(self, *, skip_crawl: bool = False) -> dict:
        """Seed NTA target pages and perform baseline crawl."""
        pages_seeded = 0

        for name, url, description, source_type in NTA_TARGET_PAGES:
            result = await self.db.execute(select(NtaTargetPage).where(NtaTargetPage.name == name))
            existing = result.scalar_one_or_none()
            if existing is None:
                page = NtaTargetPage(
                    name=name,
                    url=url,
                    description=description,
                    is_active=True,
                    source_type=source_type,
                )
                self.db.add(page)
                pages_seeded += 1

        await self.db.flush()

        if skip_crawl:
            return {"pages_seeded": pages_seeded, "pages_crawled": 0, "crawl": "skipped"}

        # Crawl all active pages
        monitor = NtaMonitor(self.db)
        changes = await monitor.check_for_changes(trigger=CrawlerRunTrigger.MANUAL)

        return {
            "pages_seeded": pages_seeded,
            "pages_crawled": len(changes),
        }

    async def _step2_seed_registry(self) -> dict:
        """Register existing hardcoded functions in AlgorithmRegistry."""
        registered = 0
        skipped = 0

        for func_name in FUNCTIONS_TO_REGISTER:
            # Check if already registered as ACTIVE
            result = await self.db.execute(
                select(AlgorithmRegistry).where(
                    AlgorithmRegistry.function_name == func_name,
                    AlgorithmRegistry.status == AlgorithmStatus.ACTIVE,
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
                status=AlgorithmStatus.ACTIVE,
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
                result = await self.db.execute(
                    select(NtaPageSnapshot)
                    .join(NtaTargetPage)
                    .where(
                        NtaTargetPage.name == page_name,
                        NtaPageSnapshot.status == SnapshotStatus.SUCCESS,
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
        results: list[VerificationResult] = []

        for page_name, func_names in NTA_PAGE_FUNCTION_MAP.items():
            # Get the latest snapshot for this page
            result = await self.db.execute(
                select(NtaPageSnapshot)
                .join(NtaTargetPage)
                .where(
                    NtaTargetPage.name == page_name,
                    NtaPageSnapshot.status == SnapshotStatus.SUCCESS,
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

                prompt = VERIFICATION_PROMPT.format(
                    nta_content=snapshot.fit_markdown,
                    function_code=source_code,
                    function_name=func_name,
                )

                try:
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
                except LlmCallError as e:
                    # Log and continue with remaining functions instead of failing entire verification
                    logger.error(
                        f"LLM verification failed for {func_name} on page {page_name}: {e}. "
                        "Skipping this function and continuing with remaining verifications."
                    )
                    continue

        await self.db.flush()

        matched = sum(1 for r in results if r.status == VerificationStatus.MATCH)
        mismatched = sum(1 for r in results if r.status == VerificationStatus.MISMATCH)
        partial = sum(1 for r in results if r.status == VerificationStatus.PARTIAL)

        return {
            "total": len(results),
            "matched": matched,
            "mismatched": mismatched,
            "partial": partial,
        }

    async def run_verification_only(self) -> dict:
        """Re-run only the LLM verification step.

        Useful after improving prompts or switching LLM providers.

        Raises:
            ValueError: If no LLM service is configured.
        """
        if not self.llm:
            raise ValueError("LLM service is required for verification")

        result = await self._step3_verify()
        await self.db.commit()
        return result
