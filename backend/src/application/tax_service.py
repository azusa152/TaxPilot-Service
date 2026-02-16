from collections.abc import Callable

from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.user_service import get_user
from src.domain import tax_calculations
from src.domain.exceptions import TaxPilotError
from src.domain.schemas import TaxCalculationResult
from src.infrastructure.algorithm_loader import AlgorithmLoader
from src.infrastructure.models import IncomeEntry, TaxProfile
from src.logging_config import get_logger

logger = get_logger(__name__)


def _get_calc_function(loader: AlgorithmLoader, name: str) -> Callable:
    """Load a calculation function from AlgorithmLoader with fallback.

    Tries the dynamic registry first. If not found (e.g., registry is empty
    or loading fails), falls back to the hardcoded functions in tax_calculations.py.
    """
    fn = loader.get_function(name)
    if fn is not None:
        return fn
    # Fallback to hardcoded functions
    func = getattr(tax_calculations, name, None)
    if func is None:
        raise ValueError(
            f"Calculation function '{name}' not found in registry or fallback"
        )
    return func


async def calculate_tax(db: AsyncSession, user_id: str, year: int) -> TaxCalculationResult:
    """Run full tax calculation for a user and year.

    Uses AlgorithmLoader for dynamic function loading with tax_calculations.py fallback.
    """
    await get_user(db, user_id)

    # Load active algorithms from registry (with fallback to hardcoded)
    # TODO: Cache AlgorithmLoader across requests to avoid repeated DB queries
    # and exec() compilation. Consider module-level singleton with TTL-based
    # refresh or FastAPI dependency injection with lifespan. For MVP, this
    # per-request instantiation is acceptable but inefficient at scale.
    loader = AlgorithmLoader()
    await loader.load_active_algorithms(db)

    result = await db.execute(
        select(TaxProfile).where(TaxProfile.user_id == user_id, TaxProfile.year == year)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise TaxPilotError(
            404,
            "TAX_PROFILE_NOT_FOUND",
            f"Tax profile for user '{user_id}', year {year} not found."
            " Create one first via PUT /tax-profiles/{user_id}/{year}.",
        )

    entries_result = await db.execute(
        select(IncomeEntry).where(
            IncomeEntry.user_id == user_id,
            IncomeEntry.payment_date.is_not(None),
            extract("year", IncomeEntry.payment_date) == year,
        )
    )
    entries = entries_result.scalars().all()
    gross_salary = sum(e.gross_amount for e in entries)

    # Load functions dynamically (registry → fallback)
    calc_salary_ded = _get_calc_function(loader, "calc_salary_income_deduction")
    calc_basic = _get_calc_function(loader, "calc_basic_deduction")
    calc_social = _get_calc_function(loader, "calc_social_insurance_deduction")
    calc_life = _get_calc_function(loader, "calc_life_insurance_deduction")
    calc_spouse_fn = _get_calc_function(loader, "calc_spouse_deduction")
    calc_deps = _get_calc_function(loader, "calc_dependents_deduction")
    calc_ideco = _get_calc_function(loader, "calc_ideco_deduction")
    calc_tax = _get_calc_function(loader, "calc_income_tax")
    calc_furusato = _get_calc_function(loader, "calc_furusato_limit")

    salary_ded = calc_salary_ded(gross_salary)
    total_income = gross_salary - salary_ded
    basic_ded = calc_basic(total_income)
    social_ded = calc_social(profile.social_insurance_premium)
    life_ded = calc_life(profile.life_insurance_premium)
    spouse_ded = calc_spouse_fn(profile.has_spouse, total_income)
    dep_ded = calc_deps(profile.dependents_count)
    ideco_ded = calc_ideco(profile.ideco_monthly_contribution)

    total_deductions = basic_ded + social_ded + life_ded + spouse_ded + dep_ded + ideco_ded
    taxable = max(0, total_income - total_deductions)
    income_tax = calc_tax(taxable)

    furusato = calc_furusato(
        gross_salary,
        profile.social_insurance_premium,
        profile.has_spouse,
        profile.dependents_count,
        profile.ideco_monthly_contribution,
    )

    logger.info(
        "Tax calculation complete for user %s, year %d: tax=%d, furusato_limit=%d",
        user_id, year, income_tax, furusato,
    )

    return TaxCalculationResult(
        user_id=user_id,
        year=year,
        gross_salary=gross_salary,
        salary_income_deduction=salary_ded,
        total_income=total_income,
        basic_deduction=basic_ded,
        social_insurance_deduction=social_ded,
        life_insurance_deduction=life_ded,
        spouse_deduction=spouse_ded,
        dependents_deduction=dep_ded,
        ideco_deduction=ideco_ded,
        total_deductions=total_deductions,
        taxable_income=taxable,
        income_tax=income_tax,
        furusato_limit=furusato,
    )
