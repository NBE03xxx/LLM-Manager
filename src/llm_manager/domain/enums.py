from enum import StrEnum


class HostKind(StrEnum):
    LOCAL = "local"
    SSH = "ssh"


class ProbeStatus(StrEnum):
    OK = "ok"
    NOT_INSTALLED = "not_installed"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"
    PERMISSION_DENIED = "permission_denied"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReportStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PlanStatus(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    BACKED_UP = "backed_up"
    APPLYING = "applying"
    VALIDATING = "validating"
    COMMITTED = "committed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    RECOVERY_REQUIRED = "recovery_required"


class ChangeOperation(StrEnum):
    CREATE_FILE = "create_file"
    REPLACE_FILE = "replace_file"
    REMOVE_CREATED_FILE = "remove_created_file"
    DAEMON_RELOAD = "daemon_reload"
    RESTART_SERVICE = "restart_service"


class ValidationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
