from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from llm_manager.application.host_discovery import DiscoverHosts, OpenSshConfigAliases
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import DiagnosticReport

from .qt_worker import PYSIDE_AVAILABLE, QtUnavailableError
from .qt_window import DiagnosisTaskFactory, MainWindow
from .composition import DiagnosticTaskFactory


def run_gui(task_factory: DiagnosisTaskFactory, locale: str, argv: Sequence[str] | None = None) -> int:
    if not PYSIDE_AVAILABLE:
        raise QtUnavailableError("pyside6_unavailable")
    from PySide6.QtWidgets import QApplication

    application = QApplication(list(argv) if argv is not None else sys.argv)
    window = MainWindow(task_factory, locale=locale)
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
    import locale as system_locale

    locale_name = system_locale.getlocale()[0] or "en"
    return run_gui(tasks, locale_name, argv)


if __name__ == "__main__":
    raise SystemExit(main())
