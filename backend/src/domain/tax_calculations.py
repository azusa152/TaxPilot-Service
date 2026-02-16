"""Deterministic Japanese tax calculation functions.

All amounts are in JPY (integers). All functions are pure — no side effects.
Reference: National Tax Agency (NTA) Japan, 2024 tax year.
"""


def calc_salary_income_deduction(gross_salary: int) -> int:
    """Calculate salary income deduction (給与所得控除).

    Based on NTA 2024 table:
    - Up to 1,625,000: 550,000
    - Up to 1,800,000: gross * 40% - 100,000
    - Up to 3,600,000: gross * 30% + 80,000
    - Up to 6,600,000: gross * 20% + 440,000
    - Up to 8,500,000: gross * 10% + 1,100,000
    - Over 8,500,000: 1,950,000 (cap)
    """
    if gross_salary <= 0:
        return 0
    if gross_salary <= 1_625_000:
        return 550_000
    if gross_salary <= 1_800_000:
        return int(gross_salary * 0.4) - 100_000
    if gross_salary <= 3_600_000:
        return int(gross_salary * 0.3) + 80_000
    if gross_salary <= 6_600_000:
        return int(gross_salary * 0.2) + 440_000
    if gross_salary <= 8_500_000:
        return int(gross_salary * 0.1) + 1_100_000
    return 1_950_000


def calc_basic_deduction(total_income: int) -> int:
    """Calculate basic deduction (基礎控除).

    2024: 480,000 for income <= 24,000,000; phased out above.
    """
    if total_income <= 24_000_000:
        return 480_000
    if total_income <= 24_500_000:
        return 320_000
    if total_income <= 25_000_000:
        return 160_000
    return 0


def calc_spouse_deduction(has_spouse: bool, taxpayer_income: int, spouse_income: int = 0) -> int:
    """Calculate spouse deduction (配偶者控除).

    Simplified 2024 rules:
    - Taxpayer income must be <= 10,000,000
    - Spouse income must be <= 480,000 (after salary deduction)
    - Base deduction: 380,000
    """
    if not has_spouse:
        return 0
    if taxpayer_income > 10_000_000:
        return 0
    if spouse_income > 480_000:
        return 0
    if taxpayer_income <= 9_000_000:
        return 380_000
    if taxpayer_income <= 9_500_000:
        return 260_000
    return 130_000


def calc_dependents_deduction(dependents_count: int) -> int:
    """Calculate dependents deduction (扶養控除).

    Simplified: 380,000 per general dependent.
    Special categories (elderly, specific) are handled via additional_attributes in future.
    """
    if dependents_count <= 0:
        return 0
    return 380_000 * dependents_count


def calc_social_insurance_deduction(premium: int) -> int:
    """Calculate social insurance deduction (社会保険料控除).

    Full amount is deductible.
    """
    return max(0, premium)


def calc_life_insurance_deduction(premium: int) -> int:
    """Calculate life insurance deduction (生命保険料控除).

    Simplified 2024 new contract rules:
    - Up to 20,000: full amount
    - Up to 40,000: premium / 2 + 10,000
    - Up to 80,000: premium / 4 + 20,000
    - Over 80,000: 40,000 (cap)
    """
    if premium <= 0:
        return 0
    if premium <= 20_000:
        return premium
    if premium <= 40_000:
        return premium // 2 + 10_000
    if premium <= 80_000:
        return premium // 4 + 20_000
    return 40_000


def calc_ideco_deduction(monthly_contribution: int) -> int:
    """Calculate iDeCo deduction (小規模企業共済等掛金控除).

    Full annual amount is deductible.
    """
    return max(0, monthly_contribution * 12)


def calc_taxable_income(
    gross_salary: int,
    social_insurance_premium: int,
    life_insurance_premium: int,
    has_spouse: bool,
    dependents_count: int,
    ideco_monthly: int,
    spouse_income: int = 0,
) -> int:
    """Calculate taxable income after all deductions.

    Returns the taxable income (課税所得) in JPY. Minimum 0.
    """
    salary_deduction = calc_salary_income_deduction(gross_salary)
    total_income = gross_salary - salary_deduction

    basic = calc_basic_deduction(total_income)
    social = calc_social_insurance_deduction(social_insurance_premium)
    life_ins = calc_life_insurance_deduction(life_insurance_premium)
    spouse = calc_spouse_deduction(has_spouse, total_income, spouse_income)
    dependents = calc_dependents_deduction(dependents_count)
    ideco = calc_ideco_deduction(ideco_monthly)

    total_deductions = basic + social + life_ins + spouse + dependents + ideco
    taxable = total_income - total_deductions

    return max(0, taxable)


def calc_income_tax(taxable_income: int) -> int:
    """Calculate income tax from taxable income (所得税).

    2024 progressive tax brackets:
    - Up to 1,950,000: 5%
    - Up to 3,300,000: 10% - 97,500
    - Up to 6,950,000: 20% - 427,500
    - Up to 9,000,000: 23% - 636,000
    - Up to 18,000,000: 33% - 1,536,000
    - Up to 40,000,000: 40% - 2,796,000
    - Over 40,000,000: 45% - 4,796,000

    Returns income tax amount (before reconstruction surtax).
    """
    if taxable_income <= 0:
        return 0
    if taxable_income <= 1_950_000:
        return int(taxable_income * 0.05)
    if taxable_income <= 3_300_000:
        return int(taxable_income * 0.10) - 97_500
    if taxable_income <= 6_950_000:
        return int(taxable_income * 0.20) - 427_500
    if taxable_income <= 9_000_000:
        return int(taxable_income * 0.23) - 636_000
    if taxable_income <= 18_000_000:
        return int(taxable_income * 0.33) - 1_536_000
    if taxable_income <= 40_000_000:
        return int(taxable_income * 0.40) - 2_796_000
    return int(taxable_income * 0.45) - 4_796_000


def calc_furusato_limit(
    gross_salary: int,
    social_insurance_premium: int,
    has_spouse: bool,
    dependents_count: int,
    ideco_monthly: int,
) -> int:
    """Calculate optimal Furusato Nouzei donation limit (ふるさと納税上限).

    Simplified formula:
    limit = (resident_tax * 20%) / (100% - income_tax_rate * 1.021 - 10%) + 2000

    This is an approximation. The exact calculation depends on marginal tax rate.
    """
    taxable = calc_taxable_income(
        gross_salary, social_insurance_premium, 0, has_spouse, dependents_count, ideco_monthly
    )

    # Approximate resident tax (10% of taxable income)
    resident_tax = int(taxable * 0.10)

    # Determine marginal income tax rate
    if taxable <= 1_950_000:
        rate = 0.05
    elif taxable <= 3_300_000:
        rate = 0.10
    elif taxable <= 6_950_000:
        rate = 0.20
    elif taxable <= 9_000_000:
        rate = 0.23
    elif taxable <= 18_000_000:
        rate = 0.33
    elif taxable <= 40_000_000:
        rate = 0.40
    else:
        rate = 0.45

    # Furusato limit formula
    denominator = 1.0 - rate * 1.021 - 0.10
    if denominator <= 0:
        return 2_000

    limit = int(resident_tax * 0.20 / denominator) + 2_000
    return max(2_000, limit)
