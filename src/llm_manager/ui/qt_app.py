from __future__ import annotations

import os
import pwd
import sys
from collections.abc import Sequence
from pathlib import Path

from llm_manager.application.host_discovery import DiscoverHosts, OpenSshConfigAliases
from llm_manager.application.apply_availability import ApplyRoute, AssessProductionApplyAvailability
from llm_manager.application.restore_availability import (
    AssessProductionRestoreAvailability,
    RestoreRoute,
)
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import DiagnosticReport, EncryptionInfo
from llm_manager.infrastructure.backup_settings import BackupSettingsStore, BuildMode

from .qt_worker import PYSIDE_AVAILABLE, QtUnavailableError
from .qt_window import ChangePlanTaskFactory as QtChangePlanTaskFactory
from .qt_window import DiagnosisTaskFactory, MainWindow
from .composition import (
    ChangePlanTaskFactory,
    DiagnosticTaskFactory,
    LocalApplyTaskFactory,
    LocalBackupInventoryTaskFactory,
    LocalRootApplyTaskFactory,
    LocalUserApplyTaskFactory,
    LocalUserRestoreTaskFactory,
    ProductionApplyTaskFactory,
    SshUserApplyTaskFactory,
)


def run_gui(
    task_factory: DiagnosisTaskFactory,
    locale: str,
    argv: Sequence[str] | None = None,
    hosts=(),
    change_plan_task_factory: QtChangePlanTaskFactory | None = None,
    backup_policy: EncryptionInfo | None = None,
    approval_actor: str = "interactive-user",
    apply_task_factory=None,
    apply_availability_service: AssessProductionApplyAvailability | None = None,
    backup_inventory_task_factory=None,
    restore_preview_task_factory=None,
    restore_task_factory=None,
    restore_availability_service: AssessProductionRestoreAvailability | None = None,
) -> int:
    if not PYSIDE_AVAILABLE:
        raise QtUnavailableError("pyside6_unavailable")
    from PySide6.QtWidgets import QApplication

    application = QApplication(list(argv) if argv is not None else sys.argv)
    window = MainWindow(
        task_factory,
        locale=locale,
        hosts=hosts,
        change_plan_task_factory=change_plan_task_factory,
        **({"backup_policy": backup_policy} if backup_policy is not None else {}),
        approval_actor=approval_actor,
        apply_task_factory=apply_task_factory,
        apply_availability_service=apply_availability_service,
        backup_inventory_task_factory=backup_inventory_task_factory,
        restore_preview_task_factory=restore_preview_task_factory,
        restore_task_factory=restore_task_factory,
        restore_availability_service=restore_availability_service,
    )
    window.resize(960, 640)
    window.show()
    return application.exec()


def unavailable_diagnosis(_host_id: str):
    def execute(_cancellation: CancellationToken) -> DiagnosticReport:
        raise RuntimeError("diagnosis_composition_unavailable")

    return execute


def main(argv: Sequence[str] | None = None) -> int:
    hosts = DiscoverHosts(OpenSshConfigAliases(Path.home() / ".ssh" / "config")).execute()
    tasks = DiagnosticTaskFactory.production(hosts)
    change_tasks = ChangePlanTaskFactory(tasks)
    configured = os.environ.get("XDG_CONFIG_HOME")
    config_root = (
        Path(configured) if configured and Path(configured).is_absolute() else Path.home() / ".config"
    )
    mode = (
        BuildMode.DEVELOPMENT
        if os.environ.get("LLM_MANAGER_DEVELOPMENT_MODE") == "1"
        else BuildMode.DISTRIBUTION
    )
    backup_policy = BackupSettingsStore(
        config_root / "llm-manager" / "backup.json"
    ).load(mode)
    actor = pwd.getpwuid(os.getuid()).pw_name
    user_apply_tasks = LocalUserApplyTaskFactory.production(hosts, tasks.local_runner)
    if tasks.local_helper_probe is None:
        raise RuntimeError("local_helper_probe_unavailable")
    root_apply_tasks = LocalRootApplyTaskFactory.production(
        hosts, tasks.local_runner, tasks.local_helper_probe
    )
    local_apply_tasks = LocalApplyTaskFactory(user_apply_tasks, root_apply_tasks)
    ssh_user_apply_tasks = SshUserApplyTaskFactory.production(tasks)
    apply_tasks = ProductionApplyTaskFactory(local_apply_tasks, ssh_user_apply_tasks)
    apply_availability = AssessProductionApplyAvailability(
        frozenset({ApplyRoute.LOCAL_USER, ApplyRoute.SSH_USER})
    )
    backup_inventory_tasks = LocalBackupInventoryTaskFactory.production(hosts)
    restore_tasks = LocalUserRestoreTaskFactory.production(hosts)
    restore_availability = AssessProductionRestoreAvailability(
        frozenset({RestoreRoute.LOCAL_USER})
    )
    import locale as system_locale

    locale_name = system_locale.getlocale()[0] or "en"
    return run_gui(
        tasks,
        locale_name,
        argv=argv,
        hosts=hosts,
        change_plan_task_factory=change_tasks,
        backup_policy=backup_policy,
        approval_actor=actor,
        apply_task_factory=apply_tasks,
        apply_availability_service=apply_availability,
        backup_inventory_task_factory=backup_inventory_tasks,
        restore_preview_task_factory=backup_inventory_tasks.preview,
        restore_task_factory=restore_tasks.task,
        restore_availability_service=restore_availability,
    )


if __name__ == "__main__":
    raise SystemExit(main())
