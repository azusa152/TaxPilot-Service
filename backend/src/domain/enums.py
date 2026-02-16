from enum import StrEnum


class IncomeType(StrEnum):
    SALARY = "SALARY"
    BONUS = "BONUS"
    OTHER = "OTHER"


class AlgorithmStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class LlmProvider(StrEnum):
    """Supported LLM providers."""

    GEMINI = "gemini"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
