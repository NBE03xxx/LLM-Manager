from __future__ import annotations

import os
import pwd
import sys
from collections.abc import Sequence
from pathlib import Path

from llm_manager.application.host_discovery import DiscoverHosts, OpenSshConfigAliases
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import DiagnosticReport, EncryptionInfo
from llm_manager.infrastructure.backup_settings import BackupSettingsStore, BuildMode

from .qt_worker import PYSIDE_AVAILABLE, QtUnavailableError
from .qt_window import ChangePlanTaskFactory as QtChangePlanTaskFactory
from .qt_window import DiagnosisTaskFactory, MainWindow
from .composition import ChangePlanTaskFactory, DiagnosticTaskFactory


def run_gui(
    task_factory: DiagnosisTaskFactory,
    locale: str,
    argv: Sequence[str] | None = None,
    hosts=(),
    change_plan_task_factory: QtChangePlanTaskFactory | None = None,
    backup_policy: EncryptionInfo | None = None,
    approval_actor: str = "interactive-user",
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
    import locale as system_locale

    locale_name = system_locale.getlocale()[0] or "en"
    return run_gui(tasks, locale_name, argv, hosts, change_tasks, backup_policy, actor)


if __name__ == "__main__":
    raise SystemExit(main())
