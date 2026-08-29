from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Generic, TypeVar

from .enums import (
    ChangeOperation,
    Confidence,
    HostKind,
    PlanStatus,
    ProbeStatus,
    ReportStatus,
    Severity,
    ValidationStatus,
)
from .errors import InvariantViolation

T = TypeVar("T")
JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | tuple["JsonValue", ...] | tuple[tuple[str, "JsonValue"], ...]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _required(value: str, field_name: str) -> None:
    if not value.strip():
        raise InvariantViolation(f"{field_name} must not be blank")


def _non_negative(value: int | None, field_name: str) -> None:
    if value is not None and value < 0:
        raise InvariantViolation(f"{field_name} must be non-negative")


@dataclass(frozen=True, slots=True)
class LocalizedMessage:
    message_key: str
    arguments: tuple[tuple[str, JsonScalar], ...] = ()
    fallback_text: str = ""

    def __post_init__(self) -> None:
        _required(self.message_key, "message_key")


@dataclass(frozen=True, slots=True)
class HostCapabilities:
    can_execute: bool = True
    can_read_files: bool = True
    can_stage_files: bool = False
    can_elevate: bool = False
    service_manager: str | None = None
    gpu_tools: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HostInfo:
    host_id: str
    kind: HostKind
    display_name: str
    capabilities: HostCapabilities
    hostname: str | None = None
    user: str | None = None
    ssh_alias: str | None = None
    fingerprint: str | None = None
    observed_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _required(self.host_id, "host_id")
        _required(self.display_name, "display_name")
        if self.kind is HostKind.SSH and not self.ssh_alias:
            raise InvariantViolation("ssh host requires ssh_alias")


@dataclass(frozen=True, slots=True)
class ProbeResult(Generic[T]):
    status: ProbeStatus
    value: T | None = None
    source: str | None = None
    observed_at: datetime = field(default_factory=utc_now)
    duration_ms: int = 0
    warnings: tuple[str, ...] = ()
    error_code: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        _non_negative(self.duration_ms, "duration_ms")
        if self.status is ProbeStatus.OK and self.value is None:
            raise InvariantViolation("successful probe requires a value")
        if self.status is not ProbeStatus.OK and self.value is not None:
            raise InvariantViolation("unsuccessful probe must not expose a value")


@dataclass(frozen=True, slots=True)
class DiskInfo:
    mount_point: str
    total_bytes: int
    free_bytes: int
    filesystem: str | None = None

    def __post_init__(self) -> None:
        _required(self.mount_point, "mount_point")
        _non_negative(self.total_bytes, "total_bytes")
        _non_negative(self.free_bytes, "free_bytes")
        if self.free_bytes > self.total_bytes:
            raise InvariantViolation("free_bytes cannot exceed total_bytes")


@dataclass(frozen=True, slots=True)
class SystemInfo:
    distribution: str
    distribution_version: str
    kernel: str
    architecture: str
    disks: tuple[DiskInfo, ...] = ()


@dataclass(frozen=True, slots=True)
class GPUInfo:
    gpu_id: str
    vendor: str
    name: str
    vram_total_bytes: int | None = None
    vram_used_bytes: int | None = None
    utilization_pct: float | None = None
    temperature_c: float | None = None
    driver_version: str | None = None
    compute_stack: str | None = None
    compute_version: str | None = None
    compute_architecture: str | None = None

    def __post_init__(self) -> None:
        _non_negative(self.vram_total_bytes, "vram_total_bytes")
        _non_negative(self.vram_used_bytes, "vram_used_bytes")
        if self.vram_total_bytes is not None and self.vram_used_bytes is not None:
            if self.vram_used_bytes > self.vram_total_bytes:
                raise InvariantViolation("used VRAM cannot exceed total VRAM")
        if self.utilization_pct is not None and not 0 <= self.utilization_pct <= 100:
            raise InvariantViolation("utilization_pct must be between 0 and 100")


@dataclass(frozen=True, slots=True)
class HardwareInfo:
    cpu: str
    logical_cores: int
    ram_total_bytes: int
    ram_available_bytes: int
    swap_total_bytes: int
    swap_free_bytes: int
    physical_cores: int | None = None
    gpus: tuple[GPUInfo, ...] = ()

    def __post_init__(self) -> None:
        if self.logical_cores <= 0:
            raise InvariantViolation("logical_cores must be positive")
        for name in ("ram_total_bytes", "ram_available_bytes", "swap_total_bytes", "swap_free_bytes"):
            _non_negative(getattr(self, name), name)
        if self.ram_available_bytes > self.ram_total_bytes:
            raise InvariantViolation("available RAM cannot exceed total RAM")
        if self.swap_free_bytes > self.swap_total_bytes:
            raise InvariantViolation("free swap cannot exceed total swap")


@dataclass(frozen=True, slots=True)
class ServiceInfo:
    unit: str
    load_state: str
    active_state: str
    sub_state: str
    enabled: bool | None = None
    fragment_path: str | None = None
    drop_in_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ObservedSetting:
    key: str
    configured: JsonScalar = None
    runtime: JsonScalar = None
    effective: JsonScalar = None
    sources: tuple[str, ...] = ()
    consistent: bool | None = None


@dataclass(frozen=True, slots=True)
class OllamaModelInfo:
    name: str
    digest: str | None = None
    size_bytes: int | None = None
    architecture: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    configured_context: int | None = None
    runtime_context: int | None = None
    loaded: bool = False
    processor: str | None = None
    cpu_memory_bytes: int | None = None
    gpu_memory_bytes: int | None = None

    def __post_init__(self) -> None:
        _required(self.name, "model name")
        for name in ("size_bytes", "configured_context", "runtime_context", "cpu_memory_bytes", "gpu_memory_bytes"):
            _non_negative(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class OllamaInfo:
    installed: bool
    version: str | None = None
    binary_path: str | None = None
    service: ServiceInfo | None = None
    environment: tuple[tuple[str, str], ...] = ()
    api_endpoint: str | None = None
    api_connectivity: ProbeStatus = ProbeStatus.UNAVAILABLE
    models: tuple[OllamaModelInfo, ...] = ()
    loaded_models: tuple[OllamaModelInfo, ...] = ()
    settings: tuple[ObservedSetting, ...] = ()


@dataclass(frozen=True, slots=True)
class OpenCodeInfo:
    installed: bool
    version: str | None = None
    binary_path: str | None = None
    config_locations: tuple[str, ...] = ()
    active_config: str | None = None
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    available_providers: tuple[str, ...] = ()
    available_models: tuple[str, ...] = ()
    base_urls: tuple[str, ...] = ()
    context_settings: tuple[tuple[str, JsonScalar], ...] = ()
    timeout_settings: tuple[tuple[str, JsonScalar], ...] = ()
    ollama_compatible: bool | None = None
    parse_warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DiagnosticFinding:
    finding_id: str
    category: str
    severity: Severity
    summary: LocalizedMessage
    evidence: tuple[tuple[str, JsonScalar], ...] = ()
    possible_causes: tuple[str, ...] = ()
    affected_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    report_id: str
    schema_version: str
    host: HostInfo
    status: ReportStatus
    system: SystemInfo | None = None
    hardware: HardwareInfo | None = None
    ollama: OllamaInfo | None = None
    opencode: OpenCodeInfo | None = None
    probe_results: tuple[tuple[str, ProbeResult[object]], ...] = ()
    findings: tuple[DiagnosticFinding, ...] = ()
    started_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class OptimizationProfile:
    profile_id: str
    version: int
    name: str
    goals: tuple[str, ...]
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Risk:
    severity: Severity
    message: LocalizedMessage
    mitigations: tuple[LocalizedMessage, ...] = ()


@dataclass(frozen=True, slots=True)
class Recommendation:
    recommendation_id: str
    rule_id: str
    rule_version: int
    target: str
    setting_key: str
    current_value: JsonValue
    recommended_value: JsonValue
    reason: LocalizedMessage
    severity: Severity
    confidence: Confidence
    impact: LocalizedMessage
    risk: Risk
    requires_restart: bool
    requires_root: bool
    evidence: tuple[tuple[str, JsonScalar], ...] = ()
    actionable: bool = False
    conflicts_with: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Change:
    change_id: str
    target: str
    operation: ChangeOperation
    before: JsonValue
    after: JsonValue
    before_hash: str | None
    diff: str
    requires_root: bool = False
    requires_restart: bool = False
    rollback_operation: ChangeOperation | None = None
    validation_checks: tuple[str, ...] = ()
    source_span: tuple[int, int] | None = None
    replacement_text: str | None = None

    def __post_init__(self) -> None:
        _required(self.change_id, "change_id")
        _required(self.target, "target")
        if not isinstance(self.operation, ChangeOperation):
            raise InvariantViolation("operation must be a ChangeOperation")
        if self.rollback_operation is not None and not isinstance(
            self.rollback_operation, ChangeOperation
        ):
            raise InvariantViolation("rollback_operation must be a ChangeOperation")
        if self.source_span is not None:
            start, end = self.source_span
            if start < 0 or end < start or self.replacement_text is None:
                raise InvariantViolation("source span requires valid offsets and replacement text")


@dataclass(frozen=True, slots=True)
class ChangeSet:
    change_set_id: str
    host_id: str
    changes: tuple[Change, ...]
    content_hash: str
    status: PlanStatus = PlanStatus.DRAFT
    affected_services: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ids = [change.change_id for change in self.changes]
        if len(ids) != len(set(ids)):
            raise InvariantViolation("change IDs must be unique")


@dataclass(frozen=True, slots=True)
class OptimizationPlan:
    plan_id: str
    report_id: str
    report_hash: str
    profile: OptimizationProfile
    rule_catalog_version: str
    recommendations: tuple[Recommendation, ...]
    selected_ids: tuple[str, ...]
    change_set: ChangeSet | None = None
    status: PlanStatus = PlanStatus.DRAFT
    created_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    approval_id: str
    plan_id: str
    report_hash: str
    change_set_hash: str
    actor: str
    approved_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None

    def is_valid_for(self, plan: OptimizationPlan, now: datetime | None = None) -> bool:
        current = now or utc_now()
        return (
            plan.change_set is not None
            and self.plan_id == plan.plan_id
            and self.report_hash == plan.report_hash
            and self.change_set_hash == plan.change_set.content_hash
            and (self.expires_at is None or current < self.expires_at)
        )


@dataclass(frozen=True, slots=True)
class ValidationResult:
    validation_id: str
    scope: str
    check: str
    status: ValidationStatus
    expected: JsonValue = None
    actual: JsonValue = None
    severity: Severity = Severity.INFO
    message: LocalizedMessage | None = None
    duration_ms: int = 0
    children: tuple["ValidationResult", ...] = ()

    def __post_init__(self) -> None:
        _non_negative(self.duration_ms, "duration_ms")


@dataclass(frozen=True, slots=True)
class BackupItem:
    target: str
    existed: bool
    content_ref: str | None
    sha256: str | None
    mode: int | None = None
    uid: int | None = None
    gid: int | None = None
    selinux_context: str | None = None
    service_state: str | None = None
    storage_location: str | None = None


@dataclass(frozen=True, slots=True)
class EncryptionInfo:
    enabled: bool
    scheme: str | None = None
    envelope_version: int | None = None
    key_reference: str | None = None
    key_scope: str | None = None


@dataclass(frozen=True, slots=True)
class BackupManifest:
    backup_id: str
    schema_version: str
    plan_id: str
    host_id: str
    host_fingerprint: str | None
    items: tuple[BackupItem, ...]
    manifest_hash: str
    storage_location: str
    encryption: EncryptionInfo
    protected: bool = False
    created_at: datetime = field(default_factory=utc_now)
    retention_expires_at: datetime | None = None
    complete: bool = False
