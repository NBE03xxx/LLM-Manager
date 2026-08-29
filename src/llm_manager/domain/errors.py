class DomainError(Exception):
    """Base class for expected domain failures."""


class InvariantViolation(DomainError):
    """Raised when a domain object would be internally inconsistent."""


class InvalidTransition(DomainError):
    """Raised when the safe-apply state machine rejects a transition."""
