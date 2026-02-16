from src.infrastructure.models import (
    AlgorithmRegistry,
    IncomeEntry,
    ProfileDefinition,
    TaxProfile,
    User,
)


def test_user_model_should_have_correct_tablename():
    assert User.__tablename__ == "users"


def test_income_entry_should_have_user_foreign_key():
    columns = {c.name for c in IncomeEntry.__table__.columns}
    assert "user_id" in columns
    assert "gross_amount" in columns
    assert "raw_content" in columns


def test_tax_profile_should_have_jsonb_column():
    col = TaxProfile.__table__.columns["additional_attributes"]
    assert col is not None


def test_profile_definition_should_have_year_as_pk():
    pk_cols = [c.name for c in ProfileDefinition.__table__.primary_key.columns]
    assert pk_cols == ["year"]


def test_algorithm_registry_should_have_unique_func_version():
    constraints = [c.name for c in AlgorithmRegistry.__table__.constraints if hasattr(c, "name") and c.name]
    assert "uq_algorithm_func_version" in constraints
