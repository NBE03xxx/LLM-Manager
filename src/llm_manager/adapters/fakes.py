from __future__ import annotations

from dataclasses import dataclass, field

from llm_manager.application.ports import (
    AuditPort,
    BackupStorePort,
    BackupRequest,
    CancellationToken,
    ClientAdapter,
    CommandRequest,
    CommandResult,
    FileStat,
    HostPort,
    OllamaPort,
    PrivilegePort,
)
from llm_manager.application.errors import AdapterError
from llm_manager.domain.models import (
    BackupManifest,
    ChangeSet,
    DiagnosticReport,
    HostCapabilities,
    HostInfo,
    OllamaInfo,
    OpenCodeInfo,
    ValidationResult,
)


@dataclass(slots=True)
class FakeHostAdapter(HostPort):
    host_info: HostInfo
    files: dict[str, bytes] = field(default_factory=dict)
    command_results: dict[tuple[str, ...], CommandResult] = field(default_factory=dict)
    calls: list[tuple[str, object]] = field(default_factory=list)

    def identify(self, cancellation: CancellationToken) -> HostInfo:
        self.calls.append(("identify", cancellation))
        return self.host_info

    def capabilities(self) -> HostCapabilities:
        return self.host_info.capabilities

    def execute_readonly(self, request: CommandRequest, cancellation: CancellationToken) -> CommandResult:
        self.calls.append(("execute_readonly", request))
        if cancellation.cancelled:
            raise RuntimeError("cancelled")
        return self.command_results[request.argv]

    def stat(self, path: str, cancellation: CancellationToken) -> FileStat:
        self.calls.append(("stat", path))
        content = self.files.get(path)
        return FileStat(path=path, exists=content is not None)

    def read_file(self, path: str, max_bytes: int, cancellation: CancellationToken) -> bytes:
        self.calls.append(("read_file", path))
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        content = self.files[path]
        if len(content) > max_bytes:
            raise ValueError("file exceeds max_bytes")
        return content


@dataclass(slots=True)
class FakeOllamaAdapter(OllamaPort):
    info: OllamaInfo
    validations: tuple[ValidationResult, ...] = ()
    planned_change_set: ChangeSet | None = None
    failure_code: str | None = None
    calls: list[str] = field(default_factory=list)

    def inspect(self, host: HostPort, cancellation: CancellationToken) -> OllamaInfo:
        self.calls.append("inspect")
        if self.failure_code:
            raise AdapterError(self.failure_code, "fake Ollama failure")
        return self.info

    def validate_api(self, host: HostPort, cancellation: CancellationToken) -> tuple[ValidationResult, ...]:
        self.calls.append("validate_api")
        return self.validations

    def plan_setting_changes(
        self, report: DiagnosticReport, setting_values: tuple[tuple[str, object], ...]
    ) -> ChangeSet:
        self.calls.append("plan_setting_changes")
        if self.planned_change_set is None:
            raise AdapterError("not_configured", "fake plan is not configured")
        return self.planned_change_set


@dataclass(slots=True)
class FakeClientAdapter(ClientAdapter):
    info: OpenCodeInfo
    validations: tuple[ValidationResult, ...] = ()
    planned_change_set: ChangeSet | None = None
    failure_code: str | None = None
    client_id: str = "opencode"
    calls: list[str] = field(default_factory=list)

    def inspect(self, host: HostPort, cancellation: CancellationToken) -> OpenCodeInfo:
        self.calls.append("inspect")
        if self.failure_code:
            raise AdapterError(self.failure_code, "fake client failure")
        return self.info

    def validate(self, host: HostPort, cancellation: CancellationToken) -> tuple[ValidationResult, ...]:
        self.calls.append("validate")
        return self.validations

    def plan_changes(self, report: DiagnosticReport, setting_values: tuple[tuple[str, object], ...]) -> ChangeSet:
        self.calls.append("plan_changes")
        if self.planned_change_set is None:
            raise AdapterError("not_configured", "fake plan is not configured")
        return self.planned_change_set


@dataclass(slots=True)
class FakeBackupStore(BackupStorePort):
    manifest: BackupManifest
    validations: tuple[ValidationResult, ...] = ()
    manifests: list[BackupManifest] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)

    def create(self, request: BackupRequest, cancellation: CancellationToken) -> BackupManifest:
        self.calls.append("create")
        self.manifests.append(self.manifest)
        return self.manifest

    def verify(self, manifest: BackupManifest, cancellation: CancellationToken) -> tuple[ValidationResult, ...]:
        self.calls.append("verify")
        return self.validations

    def restore(self, manifest: BackupManifest, cancellation: CancellationToken) -> tuple[ValidationResult, ...]:
        self.calls.append("restore")
        return self.validations

    def list_manifests(self, host_id: str) -> tuple[BackupManifest, ...]:
        self.calls.append("list_manifests")
        return tuple(item for item in self.manifests if item.host_id == host_id)


@dataclass(slots=True)
class FakePrivilegeAdapter(PrivilegePort):
    host_capabilities: HostCapabilities
    validations: tuple[ValidationResult, ...] = ()
    calls: list[str] = field(default_factory=list)

    def capabilities(self) -> HostCapabilities:
        return self.host_capabilities

    def execute_declared_changes(
        self, change_set: ChangeSet, cancellation: CancellationToken
    ) -> tuple[ValidationResult, ...]:
        self.calls.append(change_set.change_set_id)
        return self.validations


@dataclass(slots=True)
class FakeAuditAdapter(AuditPort):
    events: list[tuple[str, str, tuple[tuple[str, object], ...]]] = field(default_factory=list)

    def append(self, event_type: str, correlation_id: str, fields: tuple[tuple[str, object], ...]) -> None:
        self.events.append((event_type, correlation_id, fields))
