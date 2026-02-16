class TaxPilotError(Exception):
    """Base exception with error_code for agent-friendly responses."""

    def __init__(self, status_code: int, error_code: str, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail
