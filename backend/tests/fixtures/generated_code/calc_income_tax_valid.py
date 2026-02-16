def calc_income_tax(taxable_income, fixed_tax_cut_eligible_count=0):
    """Calculate income tax based on taxable income and applicable deductions.

    Implements the progressive income tax brackets per NTA Tax Answer No. 2260.
    Includes the 2024 Fixed Tax Cut (30,000 JPY per eligible person).

    Tax year: 2024

    Args:
        taxable_income: Taxable income in JPY after all deductions.
        fixed_tax_cut_eligible_count: Number of persons eligible for the fixed tax cut.

    Returns:
        Income tax amount in JPY.
    """
    # Progressive tax brackets (NTA 2260)
    if taxable_income <= 1_950_000:
        tax = int(taxable_income * 0.05)
    elif taxable_income <= 3_300_000:
        tax = int(taxable_income * 0.10) - 97_500
    elif taxable_income <= 6_950_000:
        tax = int(taxable_income * 0.20) - 427_500
    elif taxable_income <= 9_000_000:
        tax = int(taxable_income * 0.23) - 636_000
    elif taxable_income <= 18_000_000:
        tax = int(taxable_income * 0.33) - 1_536_000
    elif taxable_income <= 40_000_000:
        tax = int(taxable_income * 0.40) - 2_796_000
    else:
        tax = int(taxable_income * 0.45) - 4_796_000

    # 2024 Fixed Tax Cut: 30,000 JPY per eligible person
    fixed_tax_cut = 30_000 * fixed_tax_cut_eligible_count
    tax = max(0, tax - fixed_tax_cut)

    return tax
