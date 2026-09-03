from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from llm_manager.adapters.clients.opencode import OpenCodeReadOnlyAdapter
from llm_manager.adapters.host.local import LocalHostAdapter
from llm_manager.adapters.host.openssh import OpenSshHostAdapter
from llm_manager.adapters.ollama.readonly import OllamaReadOnlyAdapter
from llm_manager.application.host_discovery import HostCandidate
from llm_manager.application.change_planning import BuildSelectedOpenCodeChangePlan
from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.application.services import DiagnoseHost
from llm_manager.application.validation import ProductRuntimeValidator
from llm_manager.diagnostics.linux import LinuxSystemProbe
from llm_manager.domain.enums import HostKind
from llm_manager.domain.models import ApprovalRecord, DiagnosticReport, OptimizationPlan
from llm_manager.infrastructure.audit import LocalAuditLog
from llm_manager.infrastructure.backup import LocalBackupStore, _within
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher, BackupKeyProvider
from llm_manager.infrastructure.journal import LocalOperationJournal
from llm_manager.infrastructure.process import ProcessPolicy, SubprocessRunner
from llm_manager.infrastructure.safe_apply import AtomicFileExecutor, FileValidator, SafeApplyCoordinator
from llm_manager.infrastructure.secret_service import SecretServiceKeyProvider, SecretStorageBackend
from llm_manager.infrastructure.openssh_identity import OpenSshHostIdentityResolver
from llm_manager.infrastructure.ssh_auth import (
    ExternalTerminalSshBroker,
    SshAliasAuthRequest,
    detect_terminal,
)

_LOCAL_EXECUTABLES = frozenset(
    {"curl", "df", "lscpu", "lspci", "nvidia-smi", "ollama", "opencode", "rocm-smi", "systemctl", "uname"}
)


@dataclass(slots=True)
class DiagnosticTaskFactory:
    hosts: tuple[HostCandidate, ...]
    local_runner: SubprocessRunner
    ssh_runner: SubprocessRunner
    local_config_candidates: tuple[str, ...]
    remote_config_candidates: tuple[str, ...] = ()
    ssh_auth_broker: ExternalTerminalSshBroker | None = None

    @classmethod
    def production(cls, hosts: tuple[HostCandidate, ...]) -> "DiagnosticTaskFactory":
        ssh_runner = SubprocessRunner(ProcessPolicy(frozenset({"ssh"})))
        terminal = detect_terminal()
        runtime_base = os.environ.get("XDG_RUNTIME_DIR")
        runtime_root = Path(runtime_base) if runtime_base and Path(runtime_base).is_absolute() else Path(
            f"/run/user/{os.getuid()}"
        )
        return cls(
            hosts=hosts,
            local_runner=SubprocessRunner(ProcessPolicy(_LOCAL_EXECUTABLES)),
            ssh_runner=ssh_runner,
            local_config_candidates=_local_opencode_candidates(),
            ssh_auth_broker=(
                ExternalTerminalSshBroker(ssh_runner, runtime_root / "llm-manager", terminal)
                if terminal is not None
                else None
            ),
        )

    def __call__(self, host_id: str):
        candidate = next((item for item in self.hosts if item.host_id == host_id), None)
        if candidate is None:
            raise ValueError("unknown_host_candidate")
        report_id = f"diagnosis-{uuid.uuid4().hex}"

        def execute(cancellation: CancellationToken) -> DiagnosticReport:
            if candidate.kind is HostKind.LOCAL:
                return self._service(candidate).execute(report_id, cancellation)
            return self._execute_ssh(candidate, report_id, cancellation)

        return execute

    def _execute_ssh(
        self, candidate: HostCandidate, report_id: str, cancellation: CancellationToken
    ) -> DiagnosticReport:
        if candidate.ssh_alias is None:
            raise ValueError("ssh_candidate_requires_alias")
        resolver = OpenSshHostIdentityResolver(self.ssh_runner)
        session = None
        try:
            identity = resolver.resolve(candidate.ssh_alias, cancellation)
            if identity.authentication_required:
                if self.ssh_auth_broker is None:
                    raise AdapterError(
                        "authentication_required", "SSH authentication requires an external terminal"
                    )
                session = self.ssh_auth_broker.authenticate_alias(
                    SshAliasAuthRequest(candidate.ssh_alias), cancellation
                )
            return self._service(
                candidate,
                identity.fingerprint,
                session.socket_path if session is not None else None,
            ).execute(report_id, cancellation)
        finally:
            if session is not None and self.ssh_auth_broker is not None:
                self.ssh_auth_broker.close(session, CancellationToken())

    def _service(
        self,
        candidate: HostCandidate,
        verified_fingerprint: str | None = None,
        control_socket: str | None = None,
    ) -> DiagnoseHost:
        if candidate.kind is HostKind.LOCAL:
            host = LocalHostAdapter(self.local_runner, display_name=candidate.display_name)
            configs = self.local_config_candidates
        else:
            if candidate.ssh_alias is None:
                raise ValueError("ssh_candidate_requires_alias")
            host = OpenSshHostAdapter(
                candidate.ssh_alias,
                self.ssh_runner,
                candidate.display_name,
                verified_fingerprint=verified_fingerprint,
                control_socket=control_socket,
            )
            configs = self.remote_config_candidates
        return DiagnoseHost(
            host=host,
            ollama=OllamaReadOnlyAdapter(),
            client=OpenCodeReadOnlyAdapter(configs),
            system_probe=LinuxSystemProbe(),
        )


@dataclass(slots=True)
class ChangePlanTaskFactory:
    diagnostics: DiagnosticTaskFactory
    service: BuildSelectedOpenCodeChangePlan = BuildSelectedOpenCodeChangePlan()

    def __call__(self, plan: OptimizationPlan, report: DiagnosticReport):
        candidate = next(
            (item for item in self.diagnostics.hosts if item.host_id == report.host.host_id), None
        )
        if candidate is None:
            raise ValueError("unknown_host_candidate")

        def execute(cancellation: CancellationToken) -> OptimizationPlan:
            if candidate.kind is HostKind.LOCAL:
                host = LocalHostAdapter(
                    self.diagnostics.local_runner, display_name=candidate.display_name
                )
                return self.service.execute(plan, report, host, cancellation)
            return self._execute_ssh(candidate, plan, report, cancellation)

        return execute

    def _execute_ssh(
        self,
        candidate: HostCandidate,
        plan: OptimizationPlan,
        report: DiagnosticReport,
        cancellation: CancellationToken,
    ) -> OptimizationPlan:
        if candidate.ssh_alias is None:
            raise ValueError("ssh_candidate_requires_alias")
        resolver = OpenSshHostIdentityResolver(self.diagnostics.ssh_runner)
        session = None
        try:
            identity = resolver.resolve(candidate.ssh_alias, cancellation)
            if identity.authentication_required:
                broker = self.diagnostics.ssh_auth_broker
                if broker is None:
                    raise AdapterError(
                        "authentication_required",
                        "SSH authentication requires an external terminal",
                    )
                session = broker.authenticate_alias(
                    SshAliasAuthRequest(candidate.ssh_alias), cancellation
                )
            host = OpenSshHostAdapter(
                candidate.ssh_alias,
                self.diagnostics.ssh_runner,
                candidate.display_name,
                verified_fingerprint=identity.fingerprint,
                control_socket=session.socket_path if session is not None else None,
            )
            return self.service.execute(plan, report, host, cancellation)
        finally:
            if session is not None and self.diagnostics.ssh_auth_broker is not None:
                self.diagnostics.ssh_auth_broker.close(session, CancellationToken())


@dataclass(slots=True)
class LocalUserApplyTaskFactory:
    """Compose the non-privileged local OpenCode Safe Apply route."""

    hosts: tuple[HostCandidate, ...]
    local_runner: SubprocessRunner
    config_root: Path
    state_root: Path
    key_provider_factory: Callable[[], BackupKeyProvider] = lambda: SecretServiceKeyProvider(
        SecretStorageBackend()
    )

    @classmethod
    def production(
        cls, hosts: tuple[HostCandidate, ...], local_runner: SubprocessRunner
    ) -> "LocalUserApplyTaskFactory":
        return cls(hosts, local_runner, _local_config_root(), _local_state_root())

    def __post_init__(self) -> None:
        self.config_root = _safe_application_root(self.config_root, "opencode")
        self.state_root = _safe_application_root(self.state_root, "llm-manager") / "llm-manager"

    def __call__(self, plan: OptimizationPlan, approval: ApprovalRecord):
        change_set = plan.change_set
        if change_set is None or not change_set.changes:
            raise ValueError("change_set_empty")
        candidate = next(
            (item for item in self.hosts if item.host_id == change_set.host_id), None
        )
        if candidate is None or candidate.kind is not HostKind.LOCAL:
            raise ValueError("local_user_apply_requires_local_host")
        if any(change.requires_root for change in change_set.changes):
            raise ValueError("local_user_apply_rejects_root_change")
        allowed_root = self.config_root / "opencode"
        for change in change_set.changes:
            target = Path(change.target)
            if not target.is_absolute() or not _within(target.parent.resolve(), allowed_root):
                raise ValueError("local_user_apply_target_not_allowed")

        def execute(cancellation: CancellationToken):
            if not approval.is_valid_for(plan):
                raise AdapterError(
                    "invalid_approval", "approval does not match the current plan"
                )
            current_config_root = _safe_application_root(self.config_root, "opencode")
            if current_config_root / "opencode" != allowed_root:
                raise ValueError("application_root_changed")
            _prepare_private_state_root(self.state_root)
            cipher = None
            if plan.backup_policy.enabled:
                cipher = AesGcmBackupCipher(self.key_provider_factory())
            backups = LocalBackupStore(
                self.state_root / "backups", (allowed_root,), cipher
            )
            host = LocalHostAdapter(self.local_runner, display_name=candidate.display_name)
            runtime = ProductRuntimeValidator(
                host,
                OllamaReadOnlyAdapter(),
                OpenCodeReadOnlyAdapter(tuple(change.target for change in change_set.changes)),
            )
            coordinator = SafeApplyCoordinator(
                backups,
                AtomicFileExecutor((allowed_root,)),
                FileValidator(),
                LocalAuditLog(self.state_root / "audit"),
                LocalOperationJournal(self.state_root / "journal", (allowed_root,)),
                runtime,
            )
            return coordinator.execute(
                plan, approval, f"local-{uuid.uuid4().hex}", cancellation
            )

        return execute


def _local_opencode_candidates() -> tuple[str, ...]:
    root = _local_config_root()
    directory = root / "opencode"
    return tuple(str(directory / name) for name in ("opencode.jsonc", "opencode.json", "config.json"))


def _local_config_root() -> Path:
    configured = os.environ.get("XDG_CONFIG_HOME")
    return Path(configured) if configured and Path(configured).is_absolute() else Path.home() / ".config"


def _local_state_root() -> Path:
    configured = os.environ.get("XDG_STATE_HOME")
    return Path(configured) if configured and Path(configured).is_absolute() else Path.home() / ".local" / "state"


def _safe_application_root(base: Path, application: str) -> Path:
    if not base.is_absolute():
        raise ValueError("application_root_must_be_absolute")
    root = base / application
    if root.is_symlink():
        raise ValueError("application_root_symlink_rejected")
    return base.resolve()


def _prepare_private_state_root(root: Path) -> None:
    if root.is_symlink():
        raise ValueError("application_root_symlink_rejected")
    if not root.exists():
        root.mkdir(mode=0o700, parents=True)
        os.chmod(root, 0o700)
    stat = root.stat()
    if not root.is_dir() or stat.st_uid != os.getuid() or stat.st_mode & 0o077:
        raise ValueError("private_state_root_unsafe")
