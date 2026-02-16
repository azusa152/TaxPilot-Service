class TaxPilotError(Exception):
    """Base exception with error_code for agent-friendly responses."""

    def __init__(self, status_code: int, error_code: str, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail


class LlmCallError(TaxPilotError):
    """Raised when an LLM API call fails (network, auth, rate limit, etc.)."""

    def __init__(self, detail: str):
        super().__init__(status_code=502, error_code="LLM_CALL_FAILED", detail=detail)


class NotFoundError(TaxPilotError):
    """Raised when a requested resource is not found."""

    def __init__(self, detail: str):
        super().__init__(status_code=404, error_code="NOT_FOUND", detail=detail)
