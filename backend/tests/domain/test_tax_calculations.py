from src.domain.tax_calculations import (
    calc_basic_deduction,
    calc_dependents_deduction,
    calc_furusato_limit,
    calc_ideco_deduction,
    calc_income_tax,
    calc_life_insurance_deduction,
    calc_salary_income_deduction,
    calc_social_insurance_deduction,
    calc_spouse_deduction,
    calc_taxable_income,
)

# --- Salary Income Deduction ---


def test_salary_deduction_zero_income():
    assert calc_salary_income_deduction(0) == 0


def test_salary_deduction_low_income():
    assert calc_salary_income_deduction(1_000_000) == 550_000


def test_salary_deduction_mid_income():
    assert calc_salary_income_deduction(5_000_000) == 1_440_000  # 5M * 0.2 + 440K


def test_salary_deduction_high_income_cap():
    assert calc_salary_income_deduction(10_000_000) == 1_950_000


# --- Basic Deduction ---


def test_basic_deduction_standard():
    assert calc_basic_deduction(5_000_000) == 480_000


def test_basic_deduction_high_income_zero():
    assert calc_basic_deduction(26_000_000) == 0


# --- Spouse Deduction ---


def test_spouse_deduction_no_spouse():
    assert calc_spouse_deduction(False, 5_000_000) == 0


def test_spouse_deduction_standard():
    assert calc_spouse_deduction(True, 5_000_000, 0) == 380_000


def test_spouse_deduction_taxpayer_over_limit():
    assert calc_spouse_deduction(True, 11_000_000, 0) == 0


# --- Dependents ---


def test_dependents_zero():
    assert calc_dependents_deduction(0) == 0


def test_dependents_two():
    assert calc_dependents_deduction(2) == 760_000


# --- Social Insurance ---


def test_social_insurance_full_deduction():
    assert calc_social_insurance_deduction(600_000) == 600_000


# --- Life Insurance ---


def test_life_insurance_low():
    assert calc_life_insurance_deduction(15_000) == 15_000


def test_life_insurance_cap():
    assert calc_life_insurance_deduction(100_000) == 40_000


# --- iDeCo ---


def test_ideco_annual():
    assert calc_ideco_deduction(23_000) == 276_000  # 23K * 12


# --- Income Tax ---


def test_income_tax_zero():
    assert calc_income_tax(0) == 0


def test_income_tax_first_bracket():
    assert calc_income_tax(1_000_000) == 50_000  # 1M * 5%


def test_income_tax_second_bracket():
    assert calc_income_tax(3_000_000) == 202_500  # 3M * 10% - 97.5K


# --- Furusato Limit ---


def test_furusato_limit_average_salary():
    limit = calc_furusato_limit(5_000_000, 600_000, False, 0, 0)
    assert limit > 2_000  # Should be a meaningful amount
    assert limit < 200_000  # Sanity check


# --- Taxable Income ---


def test_taxable_income_should_not_be_negative():
    result = calc_taxable_income(0, 0, 0, False, 0, 0)
    assert result == 0
