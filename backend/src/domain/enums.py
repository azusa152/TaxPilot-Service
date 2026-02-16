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


class CrawlerRunTrigger(StrEnum):
    """How a crawler run was triggered."""

    MANUAL = "MANUAL"
    SCHEDULED = "SCHEDULED"


class SnapshotStatus(StrEnum):
    """Status of an individual page snapshot."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
