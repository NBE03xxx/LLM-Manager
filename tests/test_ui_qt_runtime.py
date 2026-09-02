import os
import threading
import time
import unittest
from dataclasses import replace

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
        from PySide6.QtWidgets import QComboBox, QLabel, QListWidget, QPushButton

        from llm_manager.application.host_discovery import HostCandidate
        from llm_manager.domain.enums import HostKind
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

            return lambda _token: replace(plan, change_set=change_set())

        window = MainWindow(
            task_factory,
            locale="en",
            hosts=hosts,
            change_plan_task_factory=change_plan_factory,
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
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
