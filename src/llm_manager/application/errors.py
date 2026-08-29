class ApplicationError(Exception):
    """Base class for application boundary failures."""


class AdapterError(ApplicationError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class OperationCancelled(ApplicationError):
    """Raised at a safe cancellation point."""
