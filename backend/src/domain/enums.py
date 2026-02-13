"""Pure domain enums — no framework imports allowed in this layer."""

import enum


class IncomeType(str, enum.Enum):
    """Types of income entries."""

    SALARY = "SALARY"
    BONUS = "BONUS"
    OTHER = "OTHER"


class AlgorithmStatus(str, enum.Enum):
    """Lifecycle status of a tax calculation algorithm."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
