from __future__ import annotations

import sys
from collections.abc import Sequence

from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import DiagnosticReport

from .qt_worker import PYSIDE_AVAILABLE, QtUnavailableError
from .qt_window import DiagnosisTaskFactory, MainWindow


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
