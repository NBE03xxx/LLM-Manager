from __future__ import annotations

from typing import Callable

from llm_manager.application.host_discovery import HostCandidate
from llm_manager.application.ports import CancellationToken
from llm_manager.application.optimization import stable_hash
from llm_manager.domain.enums import HostKind
from llm_manager.domain.models import DiagnosticReport, OptimizationPlan, OptimizationProfile, utc_now
from llm_manager.optimization import PROFILES

from .i18n import Catalog
from .qt_worker import PYSIDE_AVAILABLE, QtTaskRunner, QtUnavailableError, QtWorkerCoordinator
from .recommendations import (
    generate_recommendation_plan,
    present_recommendations,
    profile_by_id,
    select_recommendations,
)
from .workflow import GuiPresenter, GuiStep

DiagnosisTaskFactory = Callable[[str], Callable[[CancellationToken], DiagnosticReport]]
RecommendationPlanFactory = Callable[[DiagnosticReport, OptimizationProfile], OptimizationPlan]
ChangePlanTaskFactory = Callable[
    [OptimizationPlan, DiagnosticReport], Callable[[CancellationToken], OptimizationPlan]
]


if not PYSIDE_AVAILABLE:

    class MainWindow:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise QtUnavailableError("pyside6_unavailable")

else:
    from PySide6.QtCore import Qt, QTimer, Slot
    from PySide6.QtWidgets import (
        QCheckBox,
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
            hosts: tuple[HostCandidate, ...] = (),
            recommendation_plan_factory: RecommendationPlanFactory = generate_recommendation_plan,
            change_plan_task_factory: ChangePlanTaskFactory | None = None,
        ) -> None:
            super().__init__()
            self._task_factory = diagnosis_task_factory
            self._presenter = presenter or GuiPresenter()
            self._coordinator = coordinator or QtWorkerCoordinator()
            self._catalog = Catalog(locale)
            self._active_host_id: str | None = None
            self._nav_items: dict[GuiStep, QListWidgetItem] = {}
            self._hosts = hosts or (HostCandidate("local", HostKind.LOCAL, "Local"),)
            self._recommendation_plan_factory = recommendation_plan_factory
            self._change_plan_task_factory = change_plan_task_factory
            self._recommendation_plan: OptimizationPlan | None = None
            self._stale_timer = QTimer(self)
            self._stale_timer.setSingleShot(True)
            self._stale_timer.timeout.connect(self._expire_review)

            self._navigation = QListWidget()
            self._navigation.setObjectName("workflow-navigation")
            self._navigation.setAccessibleName("workflow-navigation")
            self._pages = QStackedWidget()
            self._host_label = QLabel()
            self._host_selector = QComboBox()
            self._host_selector.setObjectName("host-selector")
            self._host_selector.setAccessibleName("host-selector")
            self._status_label = QLabel()
            self._status_label.setObjectName("workflow-status")
            self._status_label.setAccessibleName("workflow-status")
            self._language = QComboBox()
            self._language.setObjectName("language-selector")
            self._language.setAccessibleName("language-selector")
            self._language.addItem("English", "en")
            self._language.addItem("日本語", "ja")
            for host in self._hosts:
                self._host_selector.addItem(host.display_name, host.host_id)
            self._diagnose_button = QPushButton()
            self._diagnose_button.setObjectName("start-diagnosis")
            self._diagnose_button.setAccessibleName("start-diagnosis")
            self._cancel_button = QPushButton()
            self._cancel_button.setObjectName("cancel-operation")
            self._cancel_button.setAccessibleName("cancel-operation")
            self._profile_selector = QComboBox()
            self._profile_selector.setObjectName("profile-selector")
            self._profile_selector.setAccessibleName("profile-selector")
            for profile in PROFILES:
                self._profile_selector.addItem(profile.name, profile.profile_id)
            self._recommendation_summary = QLabel()
            self._recommendation_summary.setObjectName("recommendation-summary")
            self._recommendation_summary.setAccessibleName("recommendation-summary")
            self._recommendation_list = QListWidget()
            self._recommendation_list.setObjectName("recommendation-list")
            self._recommendation_list.setAccessibleName("recommendation-list")
            self._review_button = QPushButton()
            self._review_button.setObjectName("review-selected")
            self._review_button.setAccessibleName("review-selected")
            self._review_summary = QLabel()
            self._review_summary.setObjectName("review-summary")
            self._review_summary.setAccessibleName("review-summary")
            self._review_list = QListWidget()
            self._review_list.setObjectName("review-list")
            self._review_list.setAccessibleName("review-list")
            self._approval_checkbox = QCheckBox()
            self._approval_checkbox.setObjectName("approve-change-set")
            self._approval_checkbox.setAccessibleName("approve-change-set")
            self._approval_status = QLabel()
            self._approval_status.setObjectName("approval-status")
            self._approval_status.setAccessibleName("approval-status")

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
            self._host_selector.currentIndexChanged.connect(self._select_host)
            self._diagnose_button.clicked.connect(self._start_diagnosis)
            self._cancel_button.clicked.connect(self._cancel_diagnosis)
            self._profile_selector.currentIndexChanged.connect(self._change_profile)
            self._recommendation_list.itemChanged.connect(self._selection_changed)
            self._review_button.clicked.connect(self._review_selected)
            self._approval_checkbox.toggled.connect(self._toggle_approval)
            self._navigation.setCurrentRow(0)
            self._language.setCurrentIndex(1 if self._catalog.locale == "ja" else 0)
            self._presenter.select_host(self._hosts[0].host_id)
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
                layout.addWidget(self._host_selector)
                layout.addWidget(self._language)
            elif step is GuiStep.DIAGNOSE:
                layout.addWidget(self._status_label)
                layout.addWidget(self._diagnose_button)
                layout.addWidget(self._cancel_button)
            elif step is GuiStep.RECOMMENDATIONS:
                layout.addWidget(self._profile_selector)
                layout.addWidget(self._recommendation_summary)
                layout.addWidget(self._recommendation_list)
                layout.addWidget(self._review_button)
            elif step is GuiStep.REVIEW:
                layout.addWidget(self._review_summary)
                layout.addWidget(self._review_list)
                layout.addWidget(self._approval_checkbox)
                layout.addWidget(self._approval_status)
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
        def _select_host(self) -> None:
            host_id = self._host_selector.currentData()
            if isinstance(host_id, str) and not self._presenter.state.busy:
                self._presenter.select_host(host_id)
                self._render()

        @Slot()
        def _start_diagnosis(self) -> None:
            host_id = self._presenter.state.selected_host_id
            if host_id is None:
                return
            try:
                self._stale_timer.stop()
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

        @Slot()
        def _change_profile(self) -> None:
            if self._presenter.state.busy:
                return
            report = self._presenter.state.report
            profile_id = self._profile_selector.currentData()
            if report is not None and isinstance(profile_id, str):
                self._invalidate_review()
                self._recommendation_plan = self._recommendation_plan_factory(
                    report, profile_by_id(profile_id)
                )
                self._render_recommendations()

        @Slot()
        def _selection_changed(self) -> None:
            if self._recommendation_plan is None or self._presenter.state.busy:
                return
            selected = tuple(
                item.data(256)
                for index in range(self._recommendation_list.count())
                if (item := self._recommendation_list.item(index)).checkState()
                == Qt.CheckState.Checked
            )
            self._recommendation_plan = select_recommendations(
                self._recommendation_plan, selected
            )
            self._invalidate_review()
            self._review_button.setEnabled(bool(selected))

        @Slot()
        def _review_selected(self) -> None:
            if self._recommendation_plan is None or not self._recommendation_plan.selected_ids:
                return
            report = self._presenter.state.report
            if report is None:
                return
            try:
                self._presenter.begin_change_plan(stable_hash(self._recommendation_plan))
                if self._change_plan_task_factory is None:
                    raise RuntimeError("change_planning_unavailable")
                runner = QtTaskRunner(
                    self._change_plan_task_factory(self._recommendation_plan, report)
                )
                runner.signals.result.connect(self._change_plan_finished)
                runner.signals.error.connect(self._change_plan_failed)
                runner.signals.cancelled.connect(self._change_plan_cancelled)
                self._active_host_id = report.host.host_id
                self._coordinator.start(report.host.host_id, runner)
            except (RuntimeError, ValueError) as error:
                self._presenter.fail_change_plan(str(error))
                self._active_host_id = None
            self._navigation.setCurrentRow(list(GuiStep).index(GuiStep.REVIEW))
            self._render()

        @Slot(object)
        def _change_plan_finished(self, result: object) -> None:
            if not isinstance(result, OptimizationPlan) or result.change_set is None:
                self._presenter.fail_change_plan("invalid_change_plan_result")
            elif (
                self._recommendation_plan is None
                or result.plan_id != self._recommendation_plan.plan_id
                or result.selected_ids != self._recommendation_plan.selected_ids
            ):
                self._presenter.fail_change_plan("change_plan_mismatch")
            else:
                self._recommendation_plan = result
                self._presenter.finish_change_plan(
                    result.change_set.content_hash, result.expires_at
                )
                if self._presenter.state.error_code is None:
                    self._schedule_stale_expiry(result)
            self._active_host_id = None
            self._render()

        @Slot(object)
        def _change_plan_failed(self, failure: object) -> None:
            self._presenter.fail_change_plan(str(getattr(failure, "code", "worker_failed")))
            self._active_host_id = None
            self._render()

        @Slot()
        def _change_plan_cancelled(self) -> None:
            self._presenter.fail_change_plan("operation_cancelled")
            self._active_host_id = None
            self._render()

        @Slot(object)
        def _diagnosis_finished(self, report: object) -> None:
            if not isinstance(report, DiagnosticReport):
                self._presenter.fail_diagnosis("invalid_diagnostic_result")
            else:
                try:
                    self._presenter.finish_diagnosis(report)
                    self._change_profile()
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

        @Slot(bool)
        def _toggle_approval(self, checked: bool) -> None:
            if checked:
                try:
                    self._presenter.approve_plan()
                except RuntimeError:
                    self._approval_checkbox.blockSignals(True)
                    self._approval_checkbox.setChecked(False)
                    self._approval_checkbox.blockSignals(False)
                    self._render()
                    return
            else:
                self._presenter.revoke_plan()
            self._render_approval()

        @Slot()
        def _expire_review(self) -> None:
            plan = self._recommendation_plan
            if plan is not None and plan.expires_at is not None and utc_now() < plan.expires_at:
                self._schedule_stale_expiry(plan)
                return
            self._presenter.expire_plan()
            self._render()

        def _invalidate_review(self) -> None:
            self._stale_timer.stop()
            self._presenter.invalidate_plan()

        def _schedule_stale_expiry(self, plan: OptimizationPlan) -> None:
            self._stale_timer.stop()
            if plan.expires_at is None:
                return
            remaining_ms = int((plan.expires_at - utc_now()).total_seconds() * 1000)
            if remaining_ms <= 0:
                self._expire_review()
            else:
                self._stale_timer.start(min(remaining_ms, 2_147_483_647))

        def _render(self) -> None:
            state = self._presenter.state
            self.setWindowTitle(self._catalog.text("app.title"))
            self._host_label.setText(self._host_selector.currentText())
            self._status_label.setText(self._catalog.text(f"status.{state.status.value}"))
            self._diagnose_button.setText(self._catalog.text("action.diagnose"))
            self._cancel_button.setText(self._catalog.text("action.cancel"))
            self._review_button.setText(self._catalog.text("action.review_selected"))
            self._approval_checkbox.setText(self._catalog.text("action.approve"))
            self._diagnose_button.setEnabled(not state.busy)
            self._cancel_button.setEnabled(state.busy)
            self._host_selector.setEnabled(not state.busy)
            self._profile_selector.setEnabled(not state.busy)
            self._recommendation_list.setEnabled(not state.busy)
            for index, profile in enumerate(PROFILES):
                self._profile_selector.setItemText(
                    index, self._catalog.text(f"profile.{profile.profile_id}")
                )
            for step, item in self._nav_items.items():
                item.setText(self._catalog.text(f"nav.{step.value}"))
            for index, step in enumerate(GuiStep):
                page = self._pages.widget(index)
                labels = page.findChildren(QLabel)
                for label in labels:
                    if label.accessibleName() == f"placeholder-{step.value}":
                        label.setText(self._catalog.text(f"nav.{step.value}"))
            self._render_recommendations()
            self._render_review()
            self._render_approval()

        def _render_recommendations(self) -> None:
            self._recommendation_list.blockSignals(True)
            self._recommendation_list.clear()
            if self._recommendation_plan is None:
                self._recommendation_summary.setText("")
                self._review_button.setEnabled(False)
                self._recommendation_list.blockSignals(False)
                return
            view = present_recommendations(self._recommendation_plan, self._catalog)
            self._recommendation_summary.setText(view.summary)
            for recommendation in view.items:
                state = self._catalog.text(
                    "state.actionable" if recommendation.actionable else "state.read_only"
                )
                item = QListWidgetItem(
                    f"{recommendation.title}\n{recommendation.severity} · {state}\n"
                    f"{recommendation.reason}\n{recommendation.impact}"
                )
                item.setData(256, recommendation.recommendation_id)
                if recommendation.actionable:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    checked = recommendation.recommendation_id in self._recommendation_plan.selected_ids
                    item.setCheckState(
                        Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                    )
                self._recommendation_list.addItem(item)
            self._review_button.setEnabled(
                bool(self._recommendation_plan.selected_ids) and not self._presenter.state.busy
            )
            self._recommendation_list.blockSignals(False)

        def _render_review(self) -> None:
            self._review_list.clear()
            plan = self._recommendation_plan
            if plan is None:
                self._review_summary.setText("")
                return
            state = self._presenter.state
            summary = self._catalog.text("review.summary", selected=len(plan.selected_ids))
            if state.busy and state.step is GuiStep.REVIEW:
                self._review_summary.setText(summary + "\n" + self._catalog.text("review.generating"))
                return
            if state.step is GuiStep.REVIEW and state.error_code:
                self._review_summary.setText(
                    summary + "\n" + self._catalog.text("review.failed", code=state.error_code)
                )
                return
            if plan.change_set is None:
                self._review_summary.setText(summary + "\n" + self._catalog.text("review.preview_only"))
                return
            self._review_summary.setText(summary)
            for change in plan.change_set.changes:
                self._review_list.addItem(
                    self._catalog.text(
                        "review.change",
                        target=change.target,
                        diff=change.diff,
                        root=self._catalog.text("state.yes" if change.requires_root else "state.no"),
                        restart=self._catalog.text(
                            "state.yes" if change.requires_restart else "state.no"
                        ),
                    )
                )

        def _render_approval(self) -> None:
            state = self._presenter.state
            plan = self._recommendation_plan
            available = (
                plan is not None
                and plan.change_set is not None
                and state.step is GuiStep.REVIEW
                and state.error_code is None
                and not state.busy
            )
            self._approval_checkbox.blockSignals(True)
            self._approval_checkbox.setEnabled(available)
            self._approval_checkbox.setChecked(available and state.approved)
            self._approval_checkbox.blockSignals(False)
            if not available:
                self._approval_status.setText("")
            elif state.approved:
                self._approval_status.setText(self._catalog.text("review.approved"))
            else:
                self._approval_status.setText(self._catalog.text("review.approval_required"))
