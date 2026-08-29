from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from typing import Protocol, runtime_checkable

from llm_manager.domain.models import (
    BackupManifest,
    EncryptionInfo,
    ChangeSet,
    DiagnosticReport,
    HostCapabilities,
    HostInfo,
    OllamaInfo,
    OpenCodeInfo,
    HardwareInfo,
    SystemInfo,
    ValidationResult,
)


class CancellationToken:
    def __init__(self, cancelled: bool = False) -> None:
        self._event = Event()
        if cancelled:
            self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()


@dataclass(frozen=True, slots=True)
class CommandRequest:
    argv: tuple[str, ...]
    timeout_ms: int
    correlation_id: str

    def __post_init__(self) -> None:
        if not self.argv or any(not part for part in self.argv):
            raise ValueError("argv must contain non-empty arguments")
        if self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")


@dataclass(frozen=True, slots=True)
class CommandResult:
    argv_redacted: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr_redacted: str
    timed_out: bool
    duration_ms: int


@dataclass(frozen=True, slots=True)
class FileStat:
    path: str
    exists: bool
    sha256: str | None = None
    mode: int | None = None
    uid: int | None = None
    gid: int | None = None
    is_symlink: bool = False


@dataclass(frozen=True, slots=True)
class BackupRequest:
    backup_id: str
    plan_id: str
    host_id: str
    host_fingerprint: str | None
    change_set: ChangeSet
    encryption: EncryptionInfo = EncryptionInfo(enabled=False)


@runtime_checkable
class HostPort(Protocol):
    def identify(self, cancellation: CancellationToken) -> HostInfo: ...

    def capabilities(self) -> HostCapabilities: ...

    def execute_readonly(self, request: CommandRequest, cancellation: CancellationToken) -> CommandResult: ...

    def stat(self, path: str, cancellation: CancellationToken) -> FileStat: ...

    def read_file(self, path: str, max_bytes: int, cancellation: CancellationToken) -> bytes: ...


@runtime_checkable
class SystemDiagnosticsPort(Protocol):
    def inspect(
        self, host: HostPort, cancellation: CancellationToken
    ) -> tuple[SystemInfo, HardwareInfo]: ...


@runtime_checkable
class OllamaPort(Protocol):
    def inspect(self, host: HostPort, cancellation: CancellationToken) -> OllamaInfo: ...

    def validate_api(self, host: HostPort, cancellation: CancellationToken) -> tuple[ValidationResult, ...]: ...

    def plan_setting_changes(self, report: DiagnosticReport, setting_values: tuple[tuple[str, object], ...]) -> ChangeSet: ...


@runtime_checkable
class ClientAdapter(Protocol):
    client_id: str

    def inspect(self, host: HostPort, cancellation: CancellationToken) -> OpenCodeInfo: ...

    def validate(self, host: HostPort, cancellation: CancellationToken) -> tuple[ValidationResult, ...]: ...

    def plan_changes(self, report: DiagnosticReport, setting_values: tuple[tuple[str, object], ...]) -> ChangeSet: ...


@runtime_checkable
class BackupStorePort(Protocol):
    def create(self, request: BackupRequest, cancellation: CancellationToken) -> BackupManifest: ...

    def verify(self, manifest: BackupManifest, cancellation: CancellationToken) -> tuple[ValidationResult, ...]: ...

    def restore(self, manifest: BackupManifest, cancellation: CancellationToken) -> tuple[ValidationResult, ...]: ...

    def list_manifests(self, host_id: str) -> tuple[BackupManifest, ...]: ...

    def set_protected(self, host_id: str, backup_id: str, protected: bool) -> BackupManifest: ...


@runtime_checkable
class PrivilegePort(Protocol):
    def capabilities(self) -> HostCapabilities: ...

    def execute_declared_changes(
        self, change_set: ChangeSet, cancellation: CancellationToken
    ) -> tuple[ValidationResult, ...]: ...


@runtime_checkable
class AuditPort(Protocol):
    def append(self, event_type: str, correlation_id: str, fields: tuple[tuple[str, object], ...]) -> None: ...
