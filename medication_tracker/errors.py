"""Custom exceptions for the prescription tracker."""


class ValidationError(Exception):
    """Raised when a prescription fails validation.

    Carries ``errors``: a list of ``(field, message)`` tuples describing every
    problem found, so callers can surface all per-field errors at once instead
    of fixing them one at a time.
    """

    def __init__(self, errors):
        if errors is None:
            errors = []
        self.errors = list(errors)
        message = "; ".join(f"{field}: {msg}" for field, msg in self.errors) or "validation failed"
        super().__init__(message)

    @property
    def field_errors(self):
        """List of ``(field, message)`` tuples."""
        return list(self.errors)