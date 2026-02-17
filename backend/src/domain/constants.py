from typing import Any

# Tax year defaults
DEFAULT_TAX_YEAR = 2024

# Supported locales
SUPPORTED_LOCALES = ["ja", "en", "zh-TW", "zh-CN"]

# Income thresholds (JPY)
BASIC_DEDUCTION = 480_000
SALARY_DEDUCTION_MIN = 550_000

# Furusato Nouzei
FURUSATO_SELF_BURDEN = 2_000

# Profile Definition — 2024 default schema
PROFILE_DEFINITION_2024: dict[str, Any] = {
    "year": 2024,
    "fields": [
        {
            "name": "fixed_tax_cut_eligible",
            "type": "boolean",
            "required": True,
            "description": "2024 Fixed Tax Cut eligibility",
        },
        {
            "name": "fixed_tax_cut_dependents",
            "type": "integer",
            "required": False,
            "description": "Number of dependents for Fixed Tax Cut",
        },
    ],
}
