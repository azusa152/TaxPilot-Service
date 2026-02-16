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


class ProposalStatus(StrEnum):
    """Status of a schema change proposal."""

    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class VerificationStatus(StrEnum):
    """Result of verifying a formula against NTA text."""

    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    PARTIAL = "PARTIAL"


class LawChangeType(StrEnum):
    """Types of tax law changes the parser can identify."""

    THRESHOLD_UPDATE = "THRESHOLD_UPDATE"
    NEW_DEDUCTION = "NEW_DEDUCTION"
    RATE_CHANGE = "RATE_CHANGE"
    NEW_FIELD_REQUIRED = "NEW_FIELD_REQUIRED"
    BRACKET_CHANGE = "BRACKET_CHANGE"
    FORMULA_CHANGE = "FORMULA_CHANGE"
    REGULATION_REMOVED = "REGULATION_REMOVED"


class ReviewDecision(StrEnum):
    """Admin's review decision for a generated formula."""

    ACCEPT = "ACCEPT"
    MODIFY = "MODIFY"
    REGENERATE = "REGENERATE"
    SKIP_PERMANENT = "SKIP_PERMANENT"
    SKIP_MANUAL = "SKIP_MANUAL"


class NotificationEvent(StrEnum):
    """Pipeline events that can trigger notifications."""

    REGULATION_CHANGE_DETECTED = "REGULATION_CHANGE_DETECTED"
    FORMULA_READY_FOR_REVIEW = "FORMULA_READY_FOR_REVIEW"
    FORMULA_ACTIVATED = "FORMULA_ACTIVATED"
    FORMULA_REGENERATING = "FORMULA_REGENERATING"
    RUN_FAILED = "RUN_FAILED"
    DEFERRED_REMINDER = "DEFERRED_REMINDER"


class CrawlerSourceType(StrEnum):
    """Source types for the three-layer tax law monitoring system."""

    NTA_TAX_ANSWER = "NTA_TAX_ANSWER"
    MOF_TAX_REFORM = "MOF_TAX_REFORM"
    EGOV_LAW = "EGOV_LAW"
