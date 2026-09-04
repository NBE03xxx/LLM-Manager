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
from llm_manager.application.change_planning import (
    BuildSelectedOllamaChangePlan,
    BuildSelectedOpenCodeChangePlan,
)
from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import BackupStorePort, CancellationToken, RuntimeValidatorPort
from llm_manager.application.restore_preflight import PrepareLocalRestore
from llm_manager.application.restore_preview import RestoreApproval, RestorePreview
from llm_manager.application.services import DiagnoseHost
from llm_manager.application.validation import ProductRuntimeValidator
from llm_manager.diagnostics.linux import LinuxSystemProbe
from llm_manager.domain.enums import HostKind
from llm_manager.domain.models import ApprovalRecord, DiagnosticReport, OptimizationPlan
from llm_manager.infrastructure.audit import LocalAuditLog
from llm_manager.infrastructure.backup import LocalBackupStore, _within
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher, BackupKeyProvider
from llm_manager.infrastructure.journal import LocalOperationJournal
from llm_manager.infrastructure.helper_compat import (
    HelperCompatibilityApplyGate,
    HelperCompatibilityProbe,
    local_helper_compatibility_probe,
)
from llm_manager.infrastructure.helper_staging import HelperStagingStore
from llm_manager.infrastructure.local_apply_inventory import LocalApplyInventoryService
from llm_manager.infrastructure.local_restore import SingleTargetLocalRestoreExecutor
from llm_manager.infrastructure.restore_execution import (
    LocalRestoreCoordinator,
    RestoreExecutionEvidence,
    RestoreExecutionPersistenceError,
    RestoreExecutionStore,
)
from llm_manager.infrastructure.process import ProcessPolicy, SubprocessRunner
from llm_manager.infrastructure.policykit import LocalPolicyKitInvoker, PKEXEC
from llm_manager.infrastructure.privileged_apply import (
    ApprovedHelperRequestFactory,
    PrivilegedRollbackRequestFactory,
    PrivilegedSafeApplyCoordinator,
)
from llm_manager.infrastructure.safe_apply import AtomicFileExecutor, FileValidator, SafeApplyCoordinator
from llm_manager.infrastructure.secret_service import SecretServiceKeyProvider, SecretStorageBackend
from llm_manager.infrastructure.openssh_identity import OpenSshHostIdentityResolver
from llm_manager.infrastructure.ssh_auth import (
    ExternalTerminalSshBroker,
    SshAliasAuthRequest,
    detect_terminal,
)
from llm_manager.infrastructure.ssh_user_home import ResolveSshUserHome

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
    local_helper_probe: HelperCompatibilityProbe | None = None
    discover_remote_home: bool = False

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
            local_helper_probe=local_helper_compatibility_probe(
                frozenset({"0.1.0~dev0"})
            ),
            ssh_auth_broker=(
                ExternalTerminalSshBroker(ssh_runner, runtime_root / "llm-manager", terminal)
                if terminal is not None
                else None
            ),
            discover_remote_home=True,
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
            socket = session.socket_path if session is not None else None
            configs = self.remote_config_candidates
            if self.discover_remote_home:
                probe_host = OpenSshHostAdapter(
                    candidate.ssh_alias, self.ssh_runner, candidate.display_name,
                    verified_fingerprint=identity.fingerprint, control_socket=socket,
                )
                configs = ResolveSshUserHome().execute(
                    probe_host, cancellation
                ).opencode_candidates
            return self._service(candidate, identity.fingerprint, socket, configs).execute(
                report_id, cancellation
            )
        finally:
            if session is not None and self.ssh_auth_broker is not None:
                self.ssh_auth_broker.close(session, CancellationToken())

    def _service(
        self,
        candidate: HostCandidate,
        verified_fingerprint: str | None = None,
        control_socket: str | None = None,
        remote_configs: tuple[str, ...] | None = None,
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
            configs = self.remote_config_candidates if remote_configs is None else remote_configs
        return DiagnoseHost(
            host=host,
            ollama=OllamaReadOnlyAdapter(),
            client=OpenCodeReadOnlyAdapter(configs),
            system_probe=LinuxSystemProbe(),
            helper_probe=self.local_helper_probe if candidate.kind is HostKind.LOCAL else None,
        )


@dataclass(slots=True)
class ChangePlanTaskFactory:
    diagnostics: DiagnosticTaskFactory
    service: BuildSelectedOpenCodeChangePlan = BuildSelectedOpenCodeChangePlan()
    ollama_service: BuildSelectedOllamaChangePlan | None = None

    def __post_init__(self) -> None:
        if self.ollama_service is None and self.diagnostics.local_helper_probe is not None:
            self.ollama_service = BuildSelectedOllamaChangePlan(
                self.diagnostics.local_helper_probe
            )

    def __call__(self, plan: OptimizationPlan, report: DiagnosticReport):
        candidate = next(
            (item for item in self.diagnostics.hosts if item.host_id == report.host.host_id), None
        )
        if candidate is None:
            raise ValueError("unknown_host_candidate")
        route = _selected_planning_route(plan)
        if route == "ollama" and candidate.kind is not HostKind.LOCAL:
            raise ValueError("ssh_root_planning_protocol_missing")
        if route == "ollama" and self.ollama_service is None:
            raise ValueError("local_root_planning_unavailable")

        def execute(cancellation: CancellationToken) -> OptimizationPlan:
            if candidate.kind is HostKind.LOCAL:
                host = LocalHostAdapter(
                    self.diagnostics.local_runner, display_name=candidate.display_name
                )
                if route == "ollama":
                    assert self.ollama_service is not None
                    return self.ollama_service.execute(plan, report, host, cancellation)
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
            if self.diagnostics.discover_remote_home:
                candidates = ResolveSshUserHome().execute(host, cancellation).opencode_candidates
                if report.opencode is None or report.opencode.active_config not in candidates:
                    raise AdapterError(
                        "ssh_user_config_not_allowed",
                        "diagnosed OpenCode config is outside the remote user allowlist",
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
    backup_store_factory: Callable[
        [Path, tuple[Path, ...], AesGcmBackupCipher | None], BackupStorePort
    ] = LocalBackupStore
    runtime_validator_factory: Callable[
        [LocalHostAdapter, tuple[str, ...]], RuntimeValidatorPort
    ] = lambda host, candidates: ProductRuntimeValidator(
        host, OllamaReadOnlyAdapter(), OpenCodeReadOnlyAdapter(candidates)
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
            backups = self.backup_store_factory(
                self.state_root / "backups", (allowed_root,), cipher
            )
            host = LocalHostAdapter(self.local_runner, display_name=candidate.display_name)
            runtime = self.runtime_validator_factory(
                host, tuple(change.target for change in change_set.changes)
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


@dataclass(slots=True)
class LocalRootApplyTaskFactory:
    """Compose the fixed local Ollama PolicyKit Safe Apply route."""

    hosts: tuple[HostCandidate, ...]
    local_runner: SubprocessRunner
    privilege_runner: SubprocessRunner
    state_root: Path
    staging_root: Path
    helper_probe: HelperCompatibilityProbe
    key_provider_factory: Callable[[], BackupKeyProvider] = lambda: SecretServiceKeyProvider(
        SecretStorageBackend()
    )
    backup_store_factory: Callable[
        [Path, tuple[Path, ...], AesGcmBackupCipher | None], BackupStorePort
    ] = LocalBackupStore
    runtime_validator_factory: Callable[
        [LocalHostAdapter], RuntimeValidatorPort
    ] = lambda host: ProductRuntimeValidator(
        host, OllamaReadOnlyAdapter(), OpenCodeReadOnlyAdapter(())
    )
    invoker_factory: Callable[
        [HelperStagingStore, SubprocessRunner], object
    ] = lambda staging, runner: LocalPolicyKitInvoker(staging, runner)

    @classmethod
    def production(
        cls,
        hosts: tuple[HostCandidate, ...],
        local_runner: SubprocessRunner,
        helper_probe: HelperCompatibilityProbe,
    ) -> "LocalRootApplyTaskFactory":
        runtime_base = os.environ.get("XDG_RUNTIME_DIR")
        runtime_root = (
            Path(runtime_base)
            if runtime_base and Path(runtime_base).is_absolute()
            else Path(f"/run/user/{os.getuid()}")
        )
        return cls(
            hosts,
            local_runner,
            SubprocessRunner(ProcessPolicy(frozenset({PKEXEC}))),
            _local_state_root(),
            runtime_root / "llm-manager" / "helper",
            helper_probe,
        )

    def __post_init__(self) -> None:
        self.state_root = _safe_application_root(self.state_root, "llm-manager") / "llm-manager"
        if not self.staging_root.is_absolute() or self.staging_root == Path("/"):
            raise ValueError("helper_staging_root_unsafe")

    def __call__(self, plan: OptimizationPlan, approval: ApprovalRecord):
        change_set = plan.change_set
        if change_set is None or not change_set.changes:
            raise ValueError("change_set_empty")
        candidate = next(
            (item for item in self.hosts if item.host_id == change_set.host_id), None
        )
        if candidate is None or candidate.kind is not HostKind.LOCAL:
            raise ValueError("local_root_apply_requires_local_host")
        if any(not change.requires_root for change in change_set.changes):
            raise ValueError("local_root_apply_requires_root_changes")

        def execute(cancellation: CancellationToken):
            if not approval.is_valid_for(plan):
                raise AdapterError("invalid_approval", "approval does not match the current plan")
            _prepare_private_state_root(self.state_root)
            host = LocalHostAdapter(self.local_runner, display_name=candidate.display_name)
            readiness = HelperCompatibilityApplyGate(host, self.helper_probe)
            cipher = None
            if plan.backup_policy.enabled:
                cipher = AesGcmBackupCipher(self.key_provider_factory())
            system_root = Path("/etc/systemd/system")
            backups = self.backup_store_factory(
                self.state_root / "backups", (system_root,), cipher
            )
            staging = HelperStagingStore(self.staging_root, owner_uid=os.getuid())
            invoker = self.invoker_factory(staging, self.privilege_runner)
            coordinator = PrivilegedSafeApplyCoordinator(
                backups,
                ApprovedHelperRequestFactory(),
                PrivilegedRollbackRequestFactory(),
                invoker,  # type: ignore[arg-type]
                self.runtime_validator_factory(host),
                LocalOperationJournal(self.state_root / "journal", (system_root,)),
                readiness,
                LocalAuditLog(self.state_root / "audit"),
            )
            return coordinator.execute(
                plan, approval, f"local-root-{uuid.uuid4().hex}", cancellation
            )

        return execute


@dataclass(frozen=True, slots=True)
class LocalApplyTaskFactory:
    """Route local plans without allowing privilege mixing."""

    user: LocalUserApplyTaskFactory
    root: LocalRootApplyTaskFactory

    def __call__(self, plan: OptimizationPlan, approval: ApprovalRecord):
        if plan.change_set is None or not plan.change_set.changes:
            raise ValueError("change_set_empty")
        privilege = {change.requires_root for change in plan.change_set.changes}
        if len(privilege) != 1:
            raise ValueError("mixed_privilege_plan_unsupported")
        return self.root(plan, approval) if privilege == {True} else self.user(plan, approval)


@dataclass(slots=True)
class LocalBackupInventoryTaskFactory:
    """Compose strict read-only local manifest and operation-journal inventory."""

    hosts: tuple[HostCandidate, ...]
    config_root: Path
    state_root: Path

    @classmethod
    def production(cls, hosts: tuple[HostCandidate, ...]) -> "LocalBackupInventoryTaskFactory":
        return cls(hosts, _local_config_root(), _local_state_root())

    def __post_init__(self) -> None:
        self.config_root = _safe_application_root(self.config_root, "opencode")
        self.state_root = _safe_application_root(self.state_root, "llm-manager") / "llm-manager"

    def __call__(self, host_id: str):
        candidate = next((item for item in self.hosts if item.host_id == host_id), None)
        if candidate is None or candidate.kind is not HostKind.LOCAL:
            raise ValueError("local_backup_inventory_requires_local_host")

        def execute(cancellation: CancellationToken) -> tuple[object, ...]:
            if not self.state_root.exists() and not self.state_root.is_symlink():
                return ()
            _validate_private_state_root(self.state_root)
            for child in (self.state_root / "backups", self.state_root / "journal"):
                if child.is_symlink():
                    raise ValueError("application_root_symlink_rejected")
            allowed_root = self.config_root / "opencode"
            service = LocalApplyInventoryService(
                LocalBackupStore(self.state_root / "backups", (allowed_root,)),
                LocalOperationJournal(self.state_root / "journal", (allowed_root,)),
                RestoreExecutionStore(self.state_root / "restore-executions"),
            )
            return service.list_for_host(host_id, cancellation)

        return execute

    def preview(self, host_id: str, backup_id: str):
        self(host_id)

        def execute(cancellation: CancellationToken):
            if not self.state_root.exists() and not self.state_root.is_symlink():
                raise AdapterError("backup_not_found", "backup is unavailable for restore preview")
            _validate_private_state_root(self.state_root)
            allowed_root = self.config_root / "opencode"
            service = LocalApplyInventoryService(
                LocalBackupStore(self.state_root / "backups", (allowed_root,)),
                LocalOperationJournal(self.state_root / "journal", (allowed_root,)),
            )
            return service.preview_restore(host_id, backup_id, cancellation)

        return execute


@dataclass(frozen=True, slots=True)
class LocalRestoreTaskResult:
    evidence: RestoreExecutionEvidence
    persisted: bool
    persistence_error: str | None = None

    @property
    def state(self):
        return self.evidence.state

    @property
    def error_code(self) -> str | None:
        return self.evidence.error_code or self.persistence_error


@dataclass(slots=True)
class LocalUserRestoreTaskFactory:
    """Compose the non-privileged local OpenCode restore route without exposing it to Qt."""

    hosts: tuple[HostCandidate, ...]
    config_root: Path
    state_root: Path
    key_provider_factory: Callable[[], BackupKeyProvider] = lambda: SecretServiceKeyProvider(
        SecretStorageBackend()
    )

    @classmethod
    def production(cls, hosts: tuple[HostCandidate, ...]) -> "LocalUserRestoreTaskFactory":
        return cls(hosts, _local_config_root(), _local_state_root())

    def __post_init__(self) -> None:
        self.config_root = _safe_application_root(self.config_root, "opencode")
        self.state_root = _safe_application_root(self.state_root, "llm-manager") / "llm-manager"

    def prepare(
        self,
        host_id: str,
        backup_id: str,
        preview: RestorePreview,
        approval: RestoreApproval,
    ):
        self._local_candidate(host_id)

        def execute(cancellation: CancellationToken):
            return PrepareLocalRestore(self._stores(read_content=False)).execute(
                host_id, backup_id, preview, approval, cancellation
            )

        return execute

    def __call__(self, authorization):
        self._local_candidate(authorization.host_id)

        def execute(cancellation: CancellationToken):
            backups = self._stores(read_content=True)
            coordinator = LocalRestoreCoordinator(
                SingleTargetLocalRestoreExecutor(backups),
                RestoreExecutionStore(self.state_root / "restore-executions"),
                LocalAuditLog(self.state_root / "audit"),
            )
            return coordinator.execute(authorization, cancellation)

        return execute

    def task(
        self,
        host_id: str,
        backup_id: str,
        preview: RestorePreview,
        approval: RestoreApproval,
    ):
        """Keep the short-lived authorization inside one worker invocation."""
        self._local_candidate(host_id)

        def execute(cancellation: CancellationToken):
            authorization = self.prepare(host_id, backup_id, preview, approval)(cancellation)
            try:
                evidence = self(authorization)(cancellation)
                return LocalRestoreTaskResult(evidence, True)
            except RestoreExecutionPersistenceError as error:
                persisted = self._persisted_evidence(authorization.authorization_hash)
                return LocalRestoreTaskResult(error.evidence, persisted, error.cause_code)
            except (AdapterError, OSError, OperationCancelled) as error:
                evidence = self._load_evidence(authorization.authorization_hash)
                if evidence is None:
                    raise error
                return LocalRestoreTaskResult(evidence, True)

        return execute

    def _load_evidence(self, authorization_hash: str) -> RestoreExecutionEvidence | None:
        try:
            return RestoreExecutionStore(
                self.state_root / "restore-executions"
            ).load_evidence(authorization_hash)
        except AdapterError:
            return None

    def _persisted_evidence(self, authorization_hash: str) -> bool:
        return self._load_evidence(authorization_hash) is not None

    def _local_candidate(self, host_id: str) -> HostCandidate:
        candidate = next((item for item in self.hosts if item.host_id == host_id), None)
        if candidate is None or candidate.kind is not HostKind.LOCAL:
            raise ValueError("local_user_restore_requires_local_host")
        return candidate

    def _stores(self, *, read_content: bool) -> LocalBackupStore:
        if not self.state_root.exists() and not self.state_root.is_symlink():
            raise AdapterError("backup_not_found", "backup is unavailable for restore")
        _validate_private_state_root(self.state_root)
        for child in (
            self.state_root / "backups",
            self.state_root / "audit",
            self.state_root / "restore-executions",
        ):
            if child.is_symlink():
                raise ValueError("application_root_symlink_rejected")
        allowed_root = self.config_root / "opencode"
        cipher = AesGcmBackupCipher(self.key_provider_factory()) if read_content else None
        return LocalBackupStore(self.state_root / "backups", (allowed_root,), cipher)


def _local_opencode_candidates() -> tuple[str, ...]:
    root = _local_config_root()
    directory = root / "opencode"
    return tuple(str(directory / name) for name in ("opencode.jsonc", "opencode.json", "config.json"))


def _selected_planning_route(plan: OptimizationPlan) -> str:
    recommendations = {item.recommendation_id: item for item in plan.recommendations}
    try:
        targets = {recommendations[item_id].target for item_id in plan.selected_ids}
    except KeyError as error:
        raise ValueError("selection_invalid") from error
    if not targets:
        # Preserve application-layer validation and avoid selecting a privileged
        # route without an explicit root recommendation.
        return "opencode"
    if targets == {"ollama.systemd"}:
        return "ollama"
    if all(target != "ollama.systemd" for target in targets):
        return "opencode"
    raise ValueError("mixed_planning_targets_unsupported")


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
    _validate_private_state_root(root)


def _validate_private_state_root(root: Path) -> None:
    if root.is_symlink() or not root.exists():
        raise ValueError("private_state_root_unsafe")
    stat = root.stat()
    if not root.is_dir() or stat.st_uid != os.getuid() or stat.st_mode & 0o077:
        raise ValueError("private_state_root_unsafe")
