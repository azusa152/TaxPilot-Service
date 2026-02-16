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


class EvolutionRunStatus(StrEnum):
    """Status of an evolution pipeline run."""

    PENDING = "PENDING"
    CRAWLING = "CRAWLING"
    PARSING = "PARSING"
    GENERATING = "GENERATING"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    ACCEPTED = "ACCEPTED"
    MODIFIED = "MODIFIED"
    REGENERATING = "REGENERATING"
    SKIPPED = "SKIPPED"
    DEFERRED = "DEFERRED"
    FAILED = "FAILED"


class LawChangeType(StrEnum):
    """Types of tax law changes the parser can identify."""

    THRESHOLD_UPDATE = "THRESHOLD_UPDATE"
    NEW_DEDUCTION = "NEW_DEDUCTION"
    RATE_CHANGE = "RATE_CHANGE"
    NEW_FIELD_REQUIRED = "NEW_FIELD_REQUIRED"
    BRACKET_CHANGE = "BRACKET_CHANGE"
    FORMULA_CHANGE = "FORMULA_CHANGE"
    REGULATION_REMOVED = "REGULATION_REMOVED"
