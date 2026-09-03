import os
import threading
import time
import unittest
from dataclasses import replace
from datetime import timedelta

from llm_manager.ui.qt_worker import PYSIDE_AVAILABLE


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 runtime is unavailable")
class QtRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        cls.application = QApplication.instance() or QApplication([])

    def test_thread_pool_keeps_event_loop_responsive_and_emits_result(self) -> None:
        from PySide6.QtCore import QEventLoop, QThread, QTimer

        from llm_manager.ui.qt_worker import QtTaskRunner, QtWorkerCoordinator

        main_thread = QThread.currentThread()
        observed = {"sentinel": False, "result": None, "worker_thread": None}

        def task(_cancellation):
            observed["worker_thread"] = QThread.currentThread()
            time.sleep(0.05)
            return "complete"

        loop = QEventLoop()
        runner = QtTaskRunner(task)
        runner.signals.result.connect(lambda value: observed.__setitem__("result", value))
        runner.signals.finished.connect(loop.quit)
        coordinator = QtWorkerCoordinator()
        coordinator.start("host-1", runner)
        QTimer.singleShot(0, lambda: observed.__setitem__("sentinel", True))
        QTimer.singleShot(2000, loop.quit)
        loop.exec()

        self.assertTrue(observed["sentinel"])
        self.assertEqual(observed["result"], "complete")
        self.assertIsNot(observed["worker_thread"], main_thread)
        self.assertFalse(coordinator.is_active("host-1"))

    def test_cancel_reaches_shared_token_and_emits_cancelled(self) -> None:
        from PySide6.QtCore import QEventLoop, QTimer

        from llm_manager.application.errors import OperationCancelled
        from llm_manager.ui.qt_worker import QtTaskRunner, QtWorkerCoordinator

        started = threading.Event()
        observed = {"cancelled": False}

        def task(cancellation):
            started.set()
            while not cancellation.cancelled:
                time.sleep(0.005)
            raise OperationCancelled("cancelled at safe point")

        loop = QEventLoop()
        runner = QtTaskRunner(task)
        runner.signals.cancelled.connect(lambda: observed.__setitem__("cancelled", True))
        runner.signals.finished.connect(loop.quit)
        coordinator = QtWorkerCoordinator()
        coordinator.start("host-1", runner)

        def cancel_when_started() -> None:
            if started.is_set():
                coordinator.cancel("host-1")
            else:
                QTimer.singleShot(5, cancel_when_started)

        QTimer.singleShot(0, cancel_when_started)
        QTimer.singleShot(2000, loop.quit)
        loop.exec()

        self.assertTrue(observed["cancelled"])
        self.assertFalse(coordinator.is_active("host-1"))

    def test_minimal_window_constructs_and_switches_language(self) -> None:
        from PySide6.QtWidgets import QComboBox, QLabel, QPushButton

        from llm_manager.ui.qt_window import MainWindow

        window = MainWindow(lambda _host_id: lambda _token: None, locale="en")
        try:
            self.assertEqual(window.windowTitle(), "LLM Manager")
            diagnose = window.findChild(QPushButton, "start-diagnosis")
            status = window.findChild(QLabel, "workflow-status")
            language = window.findChild(QComboBox, "language-selector")
            self.assertIsNotNone(diagnose)
            self.assertIsNotNone(status)
            self.assertIsNotNone(language)
            self.assertEqual(diagnose.text(), "Diagnose")
            language.setCurrentIndex(1)
            self.application.processEvents()
            self.assertEqual(diagnose.text(), "診断する")
            self.assertEqual(status.text(), "準備完了")
        finally:
            window.close()

    def test_diagnose_button_runs_worker_and_advances_to_recommendations(self) -> None:
        from PySide6.QtCore import QEventLoop, Qt, QTimer
        from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel, QListWidget, QPushButton

        from llm_manager.application.host_discovery import HostCandidate
        from llm_manager.domain.enums import HostKind
        from llm_manager.domain.enums import PlanStatus
        from llm_manager.domain.models import utc_now
        from llm_manager.infrastructure.safe_apply import ApplyOutcome
        from llm_manager.ui.qt_window import MainWindow
        from tests.test_optimization import diagnostic

        requested = []

        def task_factory(host_id):
            requested.append(host_id)
            source = diagnostic()
            bound_report = replace(source, host=replace(source.host, host_id=host_id))
            return lambda _token: bound_report

        hosts = (
            HostCandidate("local:test", HostKind.LOCAL, "Local"),
            HostCandidate("ssh:development", HostKind.SSH, "development", "development"),
        )
        def change_plan_factory(plan, _report):
            from tests.fixtures import change_set

            return lambda _token: replace(
                plan, change_set=change_set(), expires_at=utc_now() + timedelta(milliseconds=500)
            )

        def apply_task_factory(_plan, _approval):
            return lambda _token: ApplyOutcome(PlanStatus.COMMITTED, None)

        window = MainWindow(
            task_factory,
            locale="en",
            hosts=hosts,
            change_plan_task_factory=change_plan_factory,
            apply_task_factory=apply_task_factory,
        )
        try:
            diagnose = window.findChild(QPushButton, "start-diagnosis")
            navigation = window.findChild(QListWidget, "workflow-navigation")
            status = window.findChild(QLabel, "workflow-status")
            host_selector = window.findChild(QComboBox, "host-selector")
            loop = QEventLoop()

            def finish_when_complete() -> None:
                if navigation.currentRow() == 2:
                    loop.quit()
                else:
                    QTimer.singleShot(5, finish_when_complete)

            host_selector.setCurrentIndex(1)
            diagnose.click()
            QTimer.singleShot(0, finish_when_complete)
            QTimer.singleShot(2000, loop.quit)
            loop.exec()

            self.assertEqual(navigation.currentRow(), 2)
            self.assertEqual(navigation.currentItem().text(), "Recommendations")
            self.assertEqual(status.text(), "Completed")
            self.assertTrue(diagnose.isEnabled())
            self.assertEqual(requested, ["ssh:development"])
            profile_selector = window.findChild(QComboBox, "profile-selector")
            recommendations = window.findChild(QListWidget, "recommendation-list")
            summary = window.findChild(QLabel, "recommendation-summary")
            self.assertEqual(profile_selector.count(), 3)
            self.assertIsNotNone(recommendations)
            self.assertIsNotNone(summary)
            profile_selector.setCurrentIndex(2)
            self.application.processEvents()
            self.assertEqual(recommendations.count(), 2)
            self.assertIn("2 recommendations", summary.text())
            self.assertIn("compaction.", recommendations.item(0).text())
            language = window.findChild(QComboBox, "language-selector")
            language.setCurrentIndex(1)
            self.application.processEvents()
            self.assertEqual(profile_selector.currentText(), "エージェント")
            self.assertIn("推奨 2件", summary.text())
            recommendations.item(0).setCheckState(Qt.CheckState.Checked)
            review_button = window.findChild(QPushButton, "review-selected")
            self.assertTrue(review_button.isEnabled())
            review_button.click()
            review_summary = window.findChild(QLabel, "review-summary")
            review_list = window.findChild(QListWidget, "review-list")

            review_loop = QEventLoop()

            def finish_when_planned() -> None:
                if review_list.count() == 1:
                    review_loop.quit()
                else:
                    QTimer.singleShot(5, finish_when_planned)

            QTimer.singleShot(0, finish_when_planned)
            QTimer.singleShot(2000, review_loop.quit)
            review_loop.exec()
            self.assertEqual(navigation.currentRow(), 3)
            self.assertNotIn("プレビューのみ", review_summary.text())
            self.assertEqual(review_list.count(), 1)
            self.assertIn("-old\n+new", review_list.item(0).text())
            self.assertIn("root権限: 不要", review_list.item(0).text())
            approval = window.findChild(QCheckBox, "approve-change-set")
            approval_status = window.findChild(QLabel, "approval-status")
            plaintext_ack = window.findChild(QCheckBox, "plaintext-backup-ack")
            prepare_apply = window.findChild(QPushButton, "prepare-apply")
            run_apply = window.findChild(QPushButton, "run-sandbox-apply")
            results_summary = window.findChild(QLabel, "results-summary")
            self.assertTrue(approval.isEnabled())
            self.assertFalse(approval.isChecked())
            approval.click()
            self.assertTrue(approval.isChecked())
            self.assertIn("明示承認", approval_status.text())
            self.assertFalse(plaintext_ack.isHidden())
            self.assertFalse(prepare_apply.isEnabled())
            plaintext_ack.click()
            self.assertTrue(prepare_apply.isEnabled())
            prepare_apply.click()
            self.assertEqual(navigation.currentRow(), 4)
            self.assertIn("Applyはまだ開始していません", results_summary.text())
            self.assertTrue(run_apply.isEnabled())
            run_apply.click()

            apply_loop = QEventLoop()

            def finish_when_applied() -> None:
                if "committed" in results_summary.text():
                    apply_loop.quit()
                else:
                    QTimer.singleShot(5, finish_when_applied)

            QTimer.singleShot(0, finish_when_applied)
            QTimer.singleShot(2000, apply_loop.quit)
            apply_loop.exec()
            self.assertIn("committed", results_summary.text())

            stale_loop = QEventLoop()

            def finish_when_stale() -> None:
                if navigation.currentRow() == 3 and not approval.isEnabled():
                    stale_loop.quit()
                else:
                    QTimer.singleShot(5, finish_when_stale)

            QTimer.singleShot(0, finish_when_stale)
            QTimer.singleShot(2000, stale_loop.quit)
            stale_loop.exec()
            self.assertFalse(approval.isEnabled())
            self.assertFalse(approval.isChecked())
            self.assertIn("stale_plan", review_summary.text())
        finally:
            window.close()

    def test_production_availability_keeps_root_route_disabled(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from PySide6.QtWidgets import QLabel, QPushButton

        from llm_manager.application.apply_availability import (
            ApplyRoute,
            AssessProductionApplyAvailability,
        )
        from llm_manager.application.optimization import stable_hash
        from llm_manager.ui.qt_window import MainWindow
        from llm_manager.ui.workflow import GuiPresenter, GuiState, GuiStep, WorkflowStatus
        from tests.fixtures import plan, report

        observed = report()
        template = plan()
        root_change = replace(template.change_set.changes[0], requires_root=True)
        changes = replace(
            template.change_set, host_id=observed.host.host_id, changes=(root_change,)
        )
        current = replace(
            template,
            report_id=observed.report_id,
            report_hash=stable_hash(observed),
            change_set=changes,
        )
        presenter = GuiPresenter()
        apply_factory = MagicMock()
        window = MainWindow(
            lambda _host: lambda _token: observed,
            presenter=presenter,
            apply_task_factory=apply_factory,
            apply_availability_service=AssessProductionApplyAvailability(
                frozenset({ApplyRoute.LOCAL_USER})
            ),
        )
        try:
            presenter._state = GuiState(
                step=GuiStep.RESULTS,
                status=WorkflowStatus.SUCCESS,
                selected_host_id=observed.host.host_id,
                report=observed,
                approval_id="approval-test",
            )
            window._recommendation_plan = current
            window._approval_record = SimpleNamespace(approval_id="approval-test")
            window._render_results()
            run_apply = window.findChild(QPushButton, "run-sandbox-apply")
            summary = window.findChild(QLabel, "results-summary")
            self.assertFalse(run_apply.isEnabled())
            self.assertIn("local root", summary.text())
            window._run_apply()
            apply_factory.assert_not_called()
            user_change = replace(root_change, requires_root=False)
            window._recommendation_plan = replace(
                current, change_set=replace(changes, changes=(user_change,))
            )
            window._render_results()
            self.assertTrue(run_apply.isEnabled())
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
