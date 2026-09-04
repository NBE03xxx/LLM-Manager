from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Callable

from llm_manager.application.approval import CreateApprovalRecord
from llm_manager.application.apply_availability import (
    ApplyAvailability,
    AssessProductionApplyAvailability,
)
from llm_manager.application.errors import ApplicationError
from llm_manager.application.host_discovery import HostCandidate
from llm_manager.application.ports import CancellationToken
from llm_manager.application.optimization import stable_hash
from llm_manager.application.restore_preview import (
    CreateRestoreApproval,
    RestoreApproval,
    RestorePreview,
)
from llm_manager.domain.enums import HostKind, PlanStatus
from llm_manager.domain.models import (
    ApprovalRecord,
    DiagnosticReport,
    EncryptionInfo,
    OptimizationPlan,
    OptimizationProfile,
    utc_now,
)
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
ApplyTaskFactory = Callable[
    [OptimizationPlan, ApprovalRecord], Callable[[CancellationToken], object]
]
BackupInventoryTaskFactory = Callable[
    [str], Callable[[CancellationToken], tuple[object, ...]]
]
RestorePreviewTaskFactory = Callable[
    [str, str], Callable[[CancellationToken], RestorePreview]
]
RestoreTaskFactory = Callable[
    [str, str, RestorePreview, RestoreApproval], Callable[[CancellationToken], object]
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
            backup_policy: EncryptionInfo = EncryptionInfo(enabled=False),
            approval_actor: str = "interactive-user",
            approval_service: CreateApprovalRecord = CreateApprovalRecord(),
            apply_task_factory: ApplyTaskFactory | None = None,
            apply_availability_service: AssessProductionApplyAvailability | None = None,
            backup_inventory_task_factory: BackupInventoryTaskFactory | None = None,
            restore_preview_task_factory: RestorePreviewTaskFactory | None = None,
            restore_approval_service: CreateRestoreApproval = CreateRestoreApproval(),
            restore_task_factory: RestoreTaskFactory | None = None,
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
            self._backup_policy = backup_policy
            self._approval_actor = approval_actor
            self._approval_service = approval_service
            self._approval_record: ApprovalRecord | None = None
            self._apply_task_factory = apply_task_factory
            self._apply_availability_service = apply_availability_service
            self._backup_inventory_task_factory = backup_inventory_task_factory
            self._restore_preview_task_factory = restore_preview_task_factory
            self._restore_approval_service = restore_approval_service
            self._restore_task_factory = restore_task_factory
            self._apply_outcome: object | None = None
            self._backup_inventory_items: tuple[object, ...] = ()
            self._backup_inventory_error: str | None = None
            self._restore_preview: RestorePreview | None = None
            self._restore_approval: RestoreApproval | None = None
            self._restore_preview_error: str | None = None
            self._restore_outcome: object | None = None
            self._restore_active_host_id: str | None = None
            self._stale_timer = QTimer(self)
            self._stale_timer.setSingleShot(True)
            self._stale_timer.timeout.connect(self._expire_review)
            self._restore_stale_timer = QTimer(self)
            self._restore_stale_timer.setSingleShot(True)
            self._restore_stale_timer.timeout.connect(self._expire_restore_preview)

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
            self._backup_summary = QLabel()
            self._backup_summary.setObjectName("backup-policy-summary")
            self._backup_summary.setAccessibleName("backup-policy-summary")
            self._plaintext_ack = QCheckBox()
            self._plaintext_ack.setObjectName("plaintext-backup-ack")
            self._plaintext_ack.setAccessibleName("plaintext-backup-ack")
            self._prepare_apply_button = QPushButton()
            self._prepare_apply_button.setObjectName("prepare-apply")
            self._prepare_apply_button.setAccessibleName("prepare-apply")
            self._results_summary = QLabel()
            self._results_summary.setObjectName("results-summary")
            self._results_summary.setAccessibleName("results-summary")
            self._run_apply_button = QPushButton()
            self._run_apply_button.setObjectName("run-sandbox-apply")
            self._run_apply_button.setAccessibleName("run-sandbox-apply")
            self._apply_cancel_button = QPushButton()
            self._apply_cancel_button.setObjectName("cancel-sandbox-apply")
            self._apply_cancel_button.setAccessibleName("cancel-sandbox-apply")
            self._backup_inventory_summary = QLabel()
            self._backup_inventory_summary.setObjectName("backup-inventory-summary")
            self._backup_inventory_summary.setAccessibleName("backup-inventory-summary")
            self._backup_inventory_list = QListWidget()
            self._backup_inventory_list.setObjectName("backup-inventory-list")
            self._backup_inventory_list.setAccessibleName("backup-inventory-list")
            self._refresh_backups_button = QPushButton()
            self._refresh_backups_button.setObjectName("refresh-backup-inventory")
            self._refresh_backups_button.setAccessibleName("refresh-backup-inventory")
            self._restore_preview_summary = QLabel()
            self._restore_preview_summary.setObjectName("restore-preview-summary")
            self._restore_preview_summary.setAccessibleName("restore-preview-summary")
            self._restore_preview_list = QListWidget()
            self._restore_preview_list.setObjectName("restore-preview-list")
            self._restore_preview_list.setAccessibleName("restore-preview-list")
            self._restore_approval_checkbox = QCheckBox()
            self._restore_approval_checkbox.setObjectName("approve-restore-preview")
            self._restore_approval_checkbox.setAccessibleName("approve-restore-preview")
            self._restore_approval_status = QLabel()
            self._restore_approval_status.setObjectName("restore-approval-status")
            self._restore_approval_status.setAccessibleName("restore-approval-status")
            self._run_restore_button = QPushButton()
            self._run_restore_button.setObjectName("run-restore")
            self._run_restore_button.setAccessibleName("run-restore")
            self._cancel_restore_button = QPushButton()
            self._cancel_restore_button.setObjectName("cancel-restore")
            self._cancel_restore_button.setAccessibleName("cancel-restore")

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
            self._plaintext_ack.toggled.connect(lambda _checked: self._render_approval())
            self._prepare_apply_button.clicked.connect(self._prepare_apply)
            self._run_apply_button.clicked.connect(self._run_apply)
            self._apply_cancel_button.clicked.connect(self._cancel_apply)
            self._refresh_backups_button.clicked.connect(self._refresh_backups)
            self._backup_inventory_list.currentItemChanged.connect(self._select_backup_preview)
            self._restore_approval_checkbox.toggled.connect(self._toggle_restore_approval)
            self._run_restore_button.clicked.connect(self._run_restore)
            self._cancel_restore_button.clicked.connect(self._cancel_restore)
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
                layout.addWidget(self._backup_summary)
                layout.addWidget(self._approval_checkbox)
                layout.addWidget(self._plaintext_ack)
                layout.addWidget(self._approval_status)
                layout.addWidget(self._prepare_apply_button)
            elif step is GuiStep.RESULTS:
                layout.addWidget(self._results_summary)
                layout.addWidget(self._run_apply_button)
                layout.addWidget(self._apply_cancel_button)
            elif step is GuiStep.BACKUPS:
                layout.addWidget(self._backup_inventory_summary)
                layout.addWidget(self._backup_inventory_list)
                layout.addWidget(self._refresh_backups_button)
                layout.addWidget(self._restore_preview_summary)
                layout.addWidget(self._restore_preview_list)
                layout.addWidget(self._restore_approval_checkbox)
                layout.addWidget(self._restore_approval_status)
                layout.addWidget(self._run_restore_button)
                layout.addWidget(self._cancel_restore_button)
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
            if isinstance(host_id, str) and not self._ui_busy():
                self._presenter.select_host(host_id)
                self._backup_inventory_items = ()
                self._backup_inventory_error = None
                self._invalidate_restore_preview()
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
            except (ApplicationError, RuntimeError, ValueError) as error:
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
                self._recommendation_plan = replace(
                    self._recommendation_plan_factory(report, profile_by_id(profile_id)),
                    backup_policy=self._backup_policy,
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
            self._approval_record = None
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
        def _prepare_apply(self) -> None:
            plan = self._recommendation_plan
            if plan is None:
                return
            try:
                record = self._approval_service.execute(
                    plan=plan,
                    approval_id=f"approval-{uuid.uuid4().hex}",
                    actor=self._approval_actor,
                    explicit_review=self._presenter.state.approved,
                    plaintext_backup_acknowledged=(
                        self._plaintext_ack.isChecked() if not plan.backup_policy.enabled else False
                    ),
                )
                self._approval_record = record
                self._apply_outcome = None
                self._presenter.prepare_results(record.approval_id)
                self._navigation.setCurrentRow(list(GuiStep).index(GuiStep.RESULTS))
            except (RuntimeError, ValueError) as error:
                if str(getattr(error, "code", error)) == "stale_plan":
                    self._presenter.expire_plan()
            self._render()

        @Slot()
        def _run_apply(self) -> None:
            plan = self._recommendation_plan
            approval = self._approval_record
            if plan is None or approval is None or self._apply_task_factory is None:
                return
            availability = self._apply_availability()
            if availability is not None and not availability.available:
                return
            try:
                self._presenter.begin_apply()
                runner = QtTaskRunner(self._apply_task_factory(plan, approval))
                runner.signals.result.connect(self._apply_finished)
                runner.signals.error.connect(self._apply_failed)
                runner.signals.cancelled.connect(self._apply_cancelled)
                self._active_host_id = plan.change_set.host_id if plan.change_set is not None else ""
                self._coordinator.start(self._active_host_id, runner)
            except (ApplicationError, RuntimeError, ValueError) as error:
                self._presenter.fail_apply(str(getattr(error, "code", error)))
                self._active_host_id = None
            self._render()

        @Slot(object)
        def _apply_finished(self, result: object) -> None:
            status = getattr(result, "status", None)
            if not isinstance(status, PlanStatus):
                self._presenter.fail_apply("invalid_apply_result")
            else:
                self._apply_outcome = result
                self._presenter.finish_apply(status, getattr(result, "error", None))
            self._active_host_id = None
            self._render()

        @Slot(object)
        def _apply_failed(self, failure: object) -> None:
            self._presenter.fail_apply(str(getattr(failure, "code", "worker_failed")))
            self._active_host_id = None
            self._render()

        @Slot()
        def _apply_cancelled(self) -> None:
            self._presenter.fail_apply("operation_cancelled")
            self._active_host_id = None
            self._render()

        @Slot()
        def _cancel_apply(self) -> None:
            if self._active_host_id is not None and self._coordinator.cancel(self._active_host_id):
                self._presenter.request_cancel()
                self._render()

        @Slot()
        def _expire_review(self) -> None:
            plan = self._recommendation_plan
            if plan is not None and plan.expires_at is not None and utc_now() < plan.expires_at:
                self._schedule_stale_expiry(plan)
                return
            self._approval_record = None
            self._presenter.expire_plan()
            self._navigation.setCurrentRow(list(GuiStep).index(GuiStep.REVIEW))
            self._render()

        @Slot()
        def _refresh_backups(self) -> None:
            host_id = self._presenter.state.selected_host_id
            if host_id is None or self._backup_inventory_task_factory is None:
                return
            try:
                self._restore_outcome = None
                self._invalidate_restore_preview()
                self._backup_inventory_error = None
                runner = QtTaskRunner(self._backup_inventory_task_factory(host_id))
                runner.signals.result.connect(self._backup_inventory_finished)
                runner.signals.error.connect(self._backup_inventory_failed)
                self._coordinator.start(host_id, runner)
            except (ApplicationError, RuntimeError, ValueError) as error:
                self._backup_inventory_error = str(getattr(error, "code", error))
            self._render_backups()

        @Slot(object)
        def _backup_inventory_finished(self, result: object) -> None:
            self._backup_inventory_items = tuple(result)  # type: ignore[arg-type]
            self._backup_inventory_error = None
            self._render_backups()

        @Slot(object)
        def _backup_inventory_failed(self, failure: object) -> None:
            self._invalidate_restore_preview()
            self._backup_inventory_items = ()
            self._backup_inventory_error = str(
                getattr(failure, "code", "worker_failed")
            )
            self._render_backups()

        @Slot(object, object)
        def _select_backup_preview(self, current: object, _previous: object) -> None:
            self._restore_outcome = None
            self._invalidate_restore_preview()
            host_id = self._presenter.state.selected_host_id
            backup_id = current.data(256) if current is not None else None
            if (
                host_id is None
                or not isinstance(backup_id, str)
                or self._restore_preview_task_factory is None
            ):
                self._render_backups()
                return
            try:
                runner = QtTaskRunner(self._restore_preview_task_factory(host_id, backup_id))
                runner.signals.result.connect(self._restore_preview_finished)
                runner.signals.error.connect(self._restore_preview_failed)
                self._coordinator.start(host_id, runner)
            except (ApplicationError, RuntimeError, ValueError) as error:
                self._restore_preview_error = str(getattr(error, "code", error))
            self._render_backups()

        @Slot(object)
        def _restore_preview_finished(self, result: object) -> None:
            if not isinstance(result, RestorePreview):
                self._restore_preview_error = "invalid_restore_preview"
            else:
                self._restore_preview = result
                remaining_ms = int((result.expires_at - utc_now()).total_seconds() * 1000)
                if remaining_ms <= 0:
                    self._expire_restore_preview()
                    return
                self._restore_stale_timer.start(min(remaining_ms, 2_147_483_647))
            self._render_backups()

        @Slot(object)
        def _restore_preview_failed(self, failure: object) -> None:
            self._restore_preview_error = str(getattr(failure, "code", "worker_failed"))
            self._render_backups()

        @Slot(bool)
        def _toggle_restore_approval(self, checked: bool) -> None:
            self._restore_approval = None
            preview = self._restore_preview
            if checked and preview is not None:
                try:
                    self._restore_approval = self._restore_approval_service.execute(
                        preview, f"restore-{uuid.uuid4().hex}", self._approval_actor, True
                    )
                except ApplicationError as error:
                    self._restore_preview_error = error.code
                    self._restore_approval_checkbox.blockSignals(True)
                    self._restore_approval_checkbox.setChecked(False)
                    self._restore_approval_checkbox.blockSignals(False)
            self._render_backups()

        @Slot()
        def _run_restore(self) -> None:
            host_id = self._presenter.state.selected_host_id
            preview = self._restore_preview
            approval = self._restore_approval
            if (
                self._restore_active_host_id is not None
                or host_id is None
                or preview is None
                or approval is None
                or self._restore_task_factory is None
                or not approval.is_valid_for(preview)
            ):
                return
            try:
                runner = QtTaskRunner(
                    self._restore_task_factory(
                        host_id, preview.backup_id, preview, approval
                    )
                )
                runner.signals.result.connect(self._restore_finished)
                runner.signals.error.connect(self._restore_failed)
                runner.signals.cancelled.connect(self._restore_cancelled)
                runner.signals.finished.connect(self._restore_worker_done)
                self._coordinator.start(host_id, runner)
                self._restore_active_host_id = host_id
                self._restore_outcome = None
                self._restore_preview_error = None
            except (ApplicationError, RuntimeError, ValueError) as error:
                self._restore_preview_error = str(getattr(error, "code", error))
            self._render()

        @Slot()
        def _cancel_restore(self) -> None:
            host_id = self._restore_active_host_id
            if host_id is not None:
                self._coordinator.cancel(host_id)

        @Slot(object)
        def _restore_finished(self, result: object) -> None:
            self._restore_outcome = result
            self._invalidate_restore_preview()
            self._render()

        @Slot(object)
        def _restore_failed(self, failure: object) -> None:
            self._invalidate_restore_preview(
                error=str(getattr(failure, "code", "worker_failed"))
            )
            self._render()

        @Slot()
        def _restore_cancelled(self) -> None:
            self._invalidate_restore_preview(error="operation_cancelled")
            self._render()

        @Slot()
        def _restore_worker_done(self) -> None:
            self._restore_active_host_id = None
            self._render()

        @Slot()
        def _expire_restore_preview(self) -> None:
            self._invalidate_restore_preview(error="stale_restore_preview")
            self._render_backups()

        def _invalidate_restore_preview(self, error: str | None = None) -> None:
            self._restore_stale_timer.stop()
            self._restore_preview = None
            self._restore_approval = None
            self._restore_preview_error = error
            self._restore_approval_checkbox.blockSignals(True)
            self._restore_approval_checkbox.setChecked(False)
            self._restore_approval_checkbox.blockSignals(False)

        def _ui_busy(self) -> bool:
            return self._presenter.state.busy or self._restore_active_host_id is not None

        def _invalidate_review(self) -> None:
            self._stale_timer.stop()
            self._approval_record = None
            self._apply_outcome = None
            self._plaintext_ack.blockSignals(True)
            self._plaintext_ack.setChecked(False)
            self._plaintext_ack.blockSignals(False)
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
            self._plaintext_ack.setText(self._catalog.text("review.plaintext_ack"))
            self._prepare_apply_button.setText(self._catalog.text("action.prepare_apply"))
            self._run_apply_button.setText(self._catalog.text("action.run_apply"))
            self._apply_cancel_button.setText(self._catalog.text("action.cancel"))
            self._refresh_backups_button.setText(self._catalog.text("action.refresh_backups"))
            self._restore_approval_checkbox.setText(self._catalog.text("action.approve_restore"))
            self._run_restore_button.setText(self._catalog.text("action.run_restore"))
            self._cancel_restore_button.setText(self._catalog.text("action.cancel"))
            self._diagnose_button.setEnabled(not state.busy)
            self._cancel_button.setEnabled(state.busy)
            self._host_selector.setEnabled(not self._ui_busy())
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
            self._render_results()
            self._render_backups()

        def _render_backups(self) -> None:
            selected = (
                self._backup_inventory_list.currentItem().data(256)
                if self._backup_inventory_list.currentItem() is not None else None
            )
            self._backup_inventory_list.blockSignals(True)
            self._backup_inventory_list.clear()
            self._refresh_backups_button.setEnabled(
                self._backup_inventory_task_factory is not None
                and not self._ui_busy()
            )
            if self._backup_inventory_error is not None:
                self._backup_inventory_summary.setText(
                    self._catalog.text("backups.failed", code=self._backup_inventory_error)
                )
                self._backup_inventory_list.blockSignals(False)
                self._render_restore_preview()
                return
            if self._backup_inventory_task_factory is None:
                self._backup_inventory_summary.setText(self._catalog.text("backups.unavailable"))
                self._backup_inventory_list.blockSignals(False)
                self._render_restore_preview()
                return
            if not self._backup_inventory_items:
                self._backup_inventory_summary.setText(self._catalog.text("backups.empty"))
                self._backup_inventory_list.blockSignals(False)
                self._render_restore_preview()
                return
            self._backup_inventory_summary.setText(
                self._catalog.text("backups.loaded", count=len(self._backup_inventory_items))
            )
            for value in self._backup_inventory_items:
                actions = getattr(value, "allowed_actions", ())
                self._backup_inventory_list.addItem(self._catalog.text(
                    "backups.item",
                    backup_id=getattr(value, "backup_id"),
                    state=getattr(getattr(value, "state"), "value", getattr(value, "state")),
                    local=getattr(getattr(value, "local_presence"), "value", getattr(value, "local_presence")),
                    remote=getattr(getattr(value, "remote_presence"), "value", getattr(value, "remote_presence")),
                    protected=str(bool(getattr(value, "protected"))).lower(),
                    attention=str(bool(getattr(value, "requires_attention"))).lower(),
                    restore_state=getattr(value, "restore_state", None) or "none",
                    restore_attention=str(bool(
                        getattr(value, "restore_requires_attention", False)
                    )).lower(),
                    actions=", ".join(getattr(action, "value", str(action)) for action in actions) or "none",
                ))
                self._backup_inventory_list.item(self._backup_inventory_list.count() - 1).setData(
                    256, getattr(value, "backup_id")
                )
            if selected is not None:
                for index in range(self._backup_inventory_list.count()):
                    item = self._backup_inventory_list.item(index)
                    if item.data(256) == selected:
                        self._backup_inventory_list.setCurrentItem(item)
                        break
            self._backup_inventory_list.blockSignals(False)
            self._render_restore_preview()

        def _render_restore_preview(self) -> None:
            self._restore_preview_list.clear()
            preview = self._restore_preview
            if self._restore_preview_error is not None:
                self._restore_preview_summary.setText(self._catalog.text(
                    "restore_preview.failed", code=self._restore_preview_error
                ))
            elif preview is None:
                self._restore_preview_summary.setText(self._catalog.text("restore_preview.select"))
            else:
                self._restore_preview_summary.setText(self._catalog.text(
                    "restore_preview.summary", backup_id=preview.backup_id,
                    count=len(preview.items), protected=str(preview.protected).lower(),
                ))
                for item in preview.items:
                    self._restore_preview_list.addItem(self._catalog.text(
                        "restore_preview.item", target=item.target,
                        existed=str(item.existed).lower(), sha256=item.sha256 or "none",
                        mode=oct(item.mode) if item.mode is not None else "none",
                    ))
            enabled = preview is not None and utc_now() < preview.expires_at
            self._restore_approval_checkbox.setEnabled(enabled and self._restore_active_host_id is None)
            self._restore_approval_status.setText(self._catalog.text(
                "restore_preview.running" if self._restore_active_host_id is not None
                else "restore_preview.completed" if self._restore_outcome is not None
                else "restore_preview.approved" if self._restore_approval is not None
                else "restore_preview.approval_required"
            ))
            self._run_restore_button.setEnabled(
                self._restore_task_factory is not None
                and self._restore_approval is not None
                and self._restore_active_host_id is None
                and enabled
            )
            self._cancel_restore_button.setEnabled(self._restore_active_host_id is not None)

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
            encrypted = plan is not None and plan.backup_policy.enabled
            self._backup_summary.setText(
                self._catalog.text(
                    "review.backup_encrypted" if encrypted else "review.backup_plaintext"
                )
                if plan is not None and plan.change_set is not None
                else ""
            )
            self._plaintext_ack.setVisible(available and not encrypted)
            acknowledged = encrypted or self._plaintext_ack.isChecked()
            self._prepare_apply_button.setEnabled(available and state.approved and acknowledged)
            if not available:
                self._approval_status.setText("")
            elif state.approved:
                self._approval_status.setText(self._catalog.text("review.approved"))
            else:
                self._approval_status.setText(self._catalog.text("review.approval_required"))

        def _render_results(self) -> None:
            if self._approval_record is None or self._presenter.state.step is not GuiStep.RESULTS:
                self._results_summary.setText("")
                self._run_apply_button.setEnabled(False)
                self._apply_cancel_button.setEnabled(False)
                return
            state = self._presenter.state
            availability = self._apply_availability()
            route_available = (
                self._apply_task_factory is not None
                and (availability is None or availability.available)
            )
            self._run_apply_button.setEnabled(
                route_available and not state.busy and self._apply_outcome is None
            )
            self._apply_cancel_button.setEnabled(state.busy and self._active_host_id is not None)
            if state.busy:
                self._results_summary.setText(self._catalog.text("results.running"))
            elif self._apply_outcome is None:
                message = self._catalog.text(
                    "results.prepared", approval_id=self._approval_record.approval_id
                )
                if not route_available:
                    report = self._presenter.state.report
                    if report is not None and self._recommendation_plan is not None:
                        availability = availability or AssessProductionApplyAvailability().execute(
                            self._recommendation_plan, report)
                        message += "\n" + self._catalog.text(
                            "results.production_unavailable",
                            route=self._catalog.text(f"apply.route.{availability.route.value}"),
                            reason=self._catalog.text(
                                f"apply.reason.{availability.reason_code}"
                            ),
                        )
                self._results_summary.setText(message)
            elif state.error_code:
                self._results_summary.setText(
                    self._catalog.text(
                        "results.failed",
                        status=getattr(self._apply_outcome, "status").value,
                        error=state.error_code,
                    )
                )
            else:
                self._results_summary.setText(
                    self._catalog.text(
                        "results.completed", status=getattr(self._apply_outcome, "status").value
                    )
                )

        def _apply_availability(self) -> ApplyAvailability | None:
            if self._apply_availability_service is None:
                return None
            report = self._presenter.state.report
            if report is None or self._recommendation_plan is None:
                return None
            return self._apply_availability_service.execute(
                self._recommendation_plan, report
            )
