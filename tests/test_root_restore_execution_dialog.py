import os
import time
import unittest

from llm_manager.infrastructure.root_restore_execute_client import RootRestoreExecutionUnconfirmed
from llm_manager.infrastructure.root_restore_store import (
    RootRestoreExecutionView, RootRestoreResult, RootRestoreState,
)
from llm_manager.ui.qt_root_restore_execution import RootRestoreExecutionDialog
from llm_manager.ui.qt_worker import PYSIDE_AVAILABLE, QtUnavailableError
from llm_manager.ui.root_restore_execution import RootRestoreExecutionSession
from tests.test_local_root_restore_protocol import NOW, request
from tests.test_root_restore_execution_session import ExecuteClient, StatusClient


class RootRestoreExecutionDialogBoundaryTests(unittest.TestCase):
    def test_missing_runtime(self):
        if PYSIDE_AVAILABLE: self.skipTest('runtime is available')
        with self.assertRaises(QtUnavailableError): RootRestoreExecutionDialog(None)


@unittest.skipUnless(PYSIDE_AVAILABLE, 'PySide6 runtime is unavailable')
class RootRestoreExecutionDialogRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.request = request()
        self.result = RootRestoreResult(
            self.request.request_id, self.request.request_hash, 'a' * 64,
            RootRestoreState.COMMITTED, NOW, None,
        )
        self.execute, self.status = ExecuteClient(self.result), StatusClient(RootRestoreExecutionView(None, None))
        self.session = RootRestoreExecutionSession(self.execute, self.status, self.request, clock=lambda: NOW)
        self.dialog = RootRestoreExecutionDialog(self.session, locale='ja')
        self.dialog.show()
        self.addCleanup(self.dialog.close)

    def wait(self, predicate):
        end = time.monotonic() + 3
        while not predicate() and time.monotonic() < end:
            self.app.processEvents(); time.sleep(.005)
        self.assertTrue(predicate())

    def test_exact_metadata_consent_and_single_execution(self):
        text = self.dialog.details.toPlainText()
        for value in (self.request.target, self.request.current.sha256,
                      self.request.backup.sha256, self.request.request_hash):
            self.assertIn(value, text)
        self.assertFalse(self.dialog.execute_button.isEnabled())
        self.dialog.consent_box.setChecked(True)
        self.assertTrue(self.dialog.execute_button.isEnabled())
        self.dialog.execute_button.click(); self.dialog.execute_button.click()
        self.wait(lambda: not self.dialog._active)
        self.assertEqual(self.execute.calls, 1)
        self.assertEqual(self.session.state, 'committed')
        self.assertIn('復元と検証が完了', self.dialog.status.text())
        self.assertFalse(self.dialog.execute_button.isEnabled())

    def test_unconfirmed_enables_one_status_check_without_execute_retry(self):
        self.execute.outcome = RootRestoreExecutionUnconfirmed(
            self.request.request_id, self.request.request_hash, RootRestoreState.UNKNOWN,
        )
        self.dialog.consent_box.setChecked(True); self.dialog.execute_button.click()
        self.wait(lambda: not self.dialog._active)
        self.assertTrue(self.dialog.check_button.isEnabled())
        self.dialog.check_button.click(); self.dialog.check_button.click()
        self.wait(lambda: not self.dialog._active)
        self.assertEqual((self.execute.calls, self.status.calls), (1, 1))
        self.assertIn('実行開始記録はありません', self.dialog.status.text())
        self.assertFalse(self.dialog.check_button.isEnabled())

    def test_narrow_layout_wraps_warning_and_no_button_is_default(self):
        self.dialog.resize(480, 620); self.app.processEvents()
        self.assertLessEqual(self.dialog.minimumSizeHint().width(), 480)
        self.assertTrue(self.dialog.consent_description.wordWrap())
        self.assertEqual(self.dialog.consent_box.accessibleDescription(), self.dialog.consent_description.text())
        for button in (self.dialog.execute_button, self.dialog.check_button, self.dialog.close_button):
            self.assertFalse(button.autoDefault()); self.assertFalse(button.isDefault())

    def test_close_during_noncooperative_execution_waits_and_discards_late_result(self):
        import threading
        from PySide6.QtCore import QTimer
        entered = threading.Event()
        def slow(request, token): entered.set(); time.sleep(.3); return self.result
        self.execute.execute = slow
        self.dialog.consent_box.setChecked(True); self.dialog.execute_button.click()
        self.wait(entered.is_set)
        ticks = []; timer = QTimer(); timer.setInterval(10); timer.timeout.connect(lambda: ticks.append(1)); timer.start()
        self.dialog.close()
        self.assertTrue(self.dialog.isVisible())
        self.wait(lambda: not self.dialog.isVisible())
        timer.stop()
        self.assertGreaterEqual(len(ticks), 10)
        self.assertIsNone(self.session.result)
        self.assertFalse(self.session.can_execute)


if __name__ == '__main__': unittest.main()
