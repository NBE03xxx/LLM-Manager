from __future__ import annotations

from typing import Callable

from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import DiagnosticReport

from .i18n import Catalog
from .qt_worker import PYSIDE_AVAILABLE, QtTaskRunner, QtUnavailableError, QtWorkerCoordinator
from .workflow import GuiPresenter, GuiStep

DiagnosisTaskFactory = Callable[[str], Callable[[CancellationToken], DiagnosticReport]]


if not PYSIDE_AVAILABLE:

    class MainWindow:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise QtUnavailableError("pyside6_unavailable")

else:
    from PySide6.QtCore import Slot
    from PySide6.QtWidgets import (
        QComboBox,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QPushButton,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )

    class MainWindow(QMainWindow):
        def __init__(
            self,
            diagnosis_task_factory: DiagnosisTaskFactory,
            locale: str = "en",
            presenter: GuiPresenter | None = None,
            coordinator: QtWorkerCoordinator | None = None,
        ) -> None:
            super().__init__()
            self._task_factory = diagnosis_task_factory
            self._presenter = presenter or GuiPresenter()
            self._coordinator = coordinator or QtWorkerCoordinator()
            self._catalog = Catalog(locale)
            self._active_host_id: str | None = None
            self._nav_items: dict[GuiStep, QListWidgetItem] = {}

            self._navigation = QListWidget()
            self._navigation.setObjectName("workflow-navigation")
            self._navigation.setAccessibleName("workflow-navigation")
            self._pages = QStackedWidget()
            self._host_label = QLabel()
            self._status_label = QLabel()
            self._status_label.setObjectName("workflow-status")
            self._status_label.setAccessibleName("workflow-status")
            self._language = QComboBox()
            self._language.setObjectName("language-selector")
            self._language.setAccessibleName("language-selector")
            self._language.addItem("English", "en")
            self._language.addItem("日本語", "ja")
            self._diagnose_button = QPushButton()
            self._diagnose_button.setObjectName("start-diagnosis")
            self._diagnose_button.setAccessibleName("start-diagnosis")
            self._cancel_button = QPushButton()
            self._cancel_button.setObjectName("cancel-operation")
            self._cancel_button.setAccessibleName("cancel-operation")

            root = QWidget()
            layout = QHBoxLayout(root)
            layout.addWidget(self._navigation, 1)
            layout.addWidget(self._pages, 4)
            self.setCentralWidget(root)

            for step in GuiStep:
                item = QListWidgetItem()
                item.setData(256, step.value)
                self._navigation.addItem(item)
                self._nav_items[step] = item
                self._pages.addWidget(self._make_page(step))

            self._navigation.currentRowChanged.connect(self._pages.setCurrentIndex)
            self._language.currentIndexChanged.connect(self._change_language)
            self._diagnose_button.clicked.connect(self._start_diagnosis)
            self._cancel_button.clicked.connect(self._cancel_diagnosis)
            self._navigation.setCurrentRow(0)
            self._language.setCurrentIndex(1 if self._catalog.locale == "ja" else 0)
            self._presenter.select_host("local")
            self._render()

        def _make_page(self, step: GuiStep) -> QWidget:
            page = QWidget()
            page.setObjectName(f"page-{step.value}")
            page.setAccessibleName(f"page-{step.value}")
            layout = QVBoxLayout(page)
            if step is GuiStep.HOSTS:
                self._host_label.setAccessibleName("selected-host")
                self._host_label.setObjectName("selected-host")
                layout.addWidget(self._host_label)
                layout.addWidget(self._language)
            elif step is GuiStep.DIAGNOSE:
                layout.addWidget(self._status_label)
                layout.addWidget(self._diagnose_button)
                layout.addWidget(self._cancel_button)
            else:
                placeholder = QLabel()
                placeholder.setObjectName(f"placeholder-{step.value}")
                placeholder.setAccessibleName(f"placeholder-{step.value}")
                layout.addWidget(placeholder)
            layout.addStretch(1)
            return page

        @Slot()
        def _change_language(self) -> None:
            locale = self._language.currentData()
            if isinstance(locale, str):
                self._catalog = Catalog(locale)
                self._render()

        @Slot()
        def _start_diagnosis(self) -> None:
            host_id = self._presenter.state.selected_host_id
            if host_id is None:
                return
            try:
                self._presenter.begin_diagnosis()
                runner = QtTaskRunner(self._task_factory(host_id))
                runner.signals.result.connect(self._diagnosis_finished)
                runner.signals.error.connect(self._diagnosis_failed)
                runner.signals.cancelled.connect(self._diagnosis_cancelled)
                self._coordinator.start(host_id, runner)
            except (RuntimeError, ValueError) as error:
                self._presenter.fail_diagnosis(str(error))
            self._active_host_id = host_id
            self._navigation.setCurrentRow(list(GuiStep).index(GuiStep.DIAGNOSE))
            self._render()

        @Slot()
        def _cancel_diagnosis(self) -> None:
            if self._active_host_id is not None and self._coordinator.cancel(self._active_host_id):
                self._presenter.request_cancel()
                self._render()

        @Slot(object)
        def _diagnosis_finished(self, report: object) -> None:
            if not isinstance(report, DiagnosticReport):
                self._presenter.fail_diagnosis("invalid_diagnostic_result")
            else:
                try:
                    self._presenter.finish_diagnosis(report)
                except ValueError:
                    self._presenter.fail_diagnosis("report_host_mismatch")
            self._active_host_id = None
            self._navigation.setCurrentRow(list(GuiStep).index(self._presenter.state.step))
            self._render()

        @Slot(object)
        def _diagnosis_failed(self, failure: object) -> None:
            self._presenter.fail_diagnosis(str(getattr(failure, "code", "worker_failed")))
            self._active_host_id = None
            self._render()

        @Slot()
        def _diagnosis_cancelled(self) -> None:
            self._presenter.fail_diagnosis("operation_cancelled")
            self._active_host_id = None
            self._render()

        def _render(self) -> None:
            state = self._presenter.state
            self.setWindowTitle(self._catalog.text("app.title"))
            self._host_label.setText("Local")
            self._status_label.setText(self._catalog.text(f"status.{state.status.value}"))
            self._diagnose_button.setText(self._catalog.text("action.diagnose"))
            self._cancel_button.setText(self._catalog.text("action.cancel"))
            self._diagnose_button.setEnabled(not state.busy)
            self._cancel_button.setEnabled(state.busy)
            for step, item in self._nav_items.items():
                item.setText(self._catalog.text(f"nav.{step.value}"))
            for index, step in enumerate(GuiStep):
                page = self._pages.widget(index)
                labels = page.findChildren(QLabel)
                for label in labels:
                    if label.accessibleName() == f"placeholder-{step.value}":
                        label.setText(self._catalog.text(f"nav.{step.value}"))
