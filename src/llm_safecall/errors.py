class ModerationError(Exception):
    pass


class CircuitOpenError(Exception):
    pass


class PolicyViolationError(Exception):
    """Raised when input or output fails a configured policy check."""

    def __init__(self, message: str, data: dict | None = None):
        super().__init__(message)
        self.data = data or {}


class BudgetExceededError(Exception):
    pass


class RateLimitExceededError(Exception):
    pass
