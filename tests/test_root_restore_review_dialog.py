import os
import time
import unittest
from datetime import timedelta

from llm_manager.ui.qt_worker import PYSIDE_AVAILABLE, QtUnavailableError
from llm_manager.ui.qt_root_restore_review import RootRestoreReviewDialog
from llm_manager.ui.root_restore_review import RootRestoreReviewSession
from llm_manager.infrastructure.root_restore_review_client import SavedRootRestoreReview
from tests import test_root_restore_review_client as fixture


class RootReviewDialogBoundaryTests(unittest.TestCase):
    def test_missing_runtime(self):
        if PYSIDE_AVAILABLE:
            self.skipTest('runtime is available')
        with self.assertRaises(QtUnavailableError): RootRestoreReviewDialog(None)


@unittest.skipUnless(PYSIDE_AVAILABLE, 'PySide6 runtime is unavailable')
class RootReviewDialogRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        f = fixture.RootRestoreReviewClientTests()
        f.setUp()
        self.selection = f.selection
        self.calls = []
        owner = self
        class Client:
            def validate_selection(self, selection):
                f.client.validate_selection(selection)
            def preview(self, backup_id, token):
                owner.calls.append('preview')
                return owner.selection
            def approve(self, selection, *, request_id, approval_id, cancellation):
                owner.calls.append('approve')
                return SavedRootRestoreReview(request_id, selection.request(request_id, approval_id).request_hash)
        self.client = Client()
        self.session = RootRestoreReviewSession(self.client, 'backup-1', clock=lambda: fixture.NOW)
        self.dialog = RootRestoreReviewDialog(self.session, locale='ja')
        self.dialog.show()
        self.addCleanup(self.dialog.close)

    def wait(self, predicate):
        end = time.monotonic() + 3
        while not predicate() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(predicate())

    def ready(self):
        self.dialog.load_button.click()
        self.wait(lambda: not self.dialog._active)
        self.assertEqual(self.session.state, 'ready')

    def test_exact_metadata_explicit_consent_and_save_only(self):
        self.assertEqual(self.calls, [])
        self.assertFalse(self.dialog.save_button.isEnabled())
        self.ready()
        text = self.dialog.details.toPlainText()
        for value in (self.selection.target, self.selection.current.sha256,
                      self.selection.backup.sha256, self.selection.preview_hash):
            self.assertIn(value, text)
        self.assertFalse(self.dialog.save_button.isEnabled())
        self.dialog.consent_box.setChecked(True)
        self.assertTrue(self.dialog.save_button.isEnabled())
        self.dialog.save_button.click()
        self.dialog.save_button.click()
        self.wait(lambda: not self.dialog._active)
        self.assertEqual(self.calls, ['preview', 'approve'])
        self.assertEqual(self.session.state, 'saved')
        self.assertIn('設定は復元していません', self.dialog.status.text())
        self.assertFalse(self.dialog.save_button.isEnabled())
        self.assertEqual(self.dialog.save_button.accessibleName(), self.dialog.save_button.text())

    def test_history_after_failed_save_is_explicit_and_does_not_resend(self):
        from llm_manager.infrastructure.root_restore_store import RootRestoreExecutionView
        def fail(*args, **kwargs):
            self.calls.append('approve')
            raise RuntimeError('private-sentinel')
        def status(request, token):
            self.calls.append('status')
            return RootRestoreExecutionView(None, None)
        self.client.approve = fail
        self.client.status = status
        self.assertFalse(self.dialog.check_button.isEnabled())
        self.ready()
        self.dialog.consent_box.setChecked(True)
        self.dialog.save_button.click()
        self.wait(lambda: not self.dialog._active)
        self.assertTrue(self.dialog.check_button.isEnabled())
        self.assertEqual(self.calls, ['preview', 'approve'])
        self.dialog.check_button.click()
        self.dialog.check_button.click()
        self.wait(lambda: not self.dialog._active)
        self.assertEqual(self.calls, ['preview', 'approve', 'status'])
        self.assertIn('実行開始記録はありません', self.dialog.status.text())
        self.assertFalse(self.dialog.save_button.isEnabled())
        self.assertFalse(self.dialog.check_button.isEnabled())

    def test_close_during_status_discards_late_history(self):
        import threading
        from llm_manager.infrastructure.root_restore_store import RootRestoreExecutionView
        entered = threading.Event()
        def status(request, token):
            entered.set()
            time.sleep(.2)
            return RootRestoreExecutionView(None, None)
        self.client.status = status
        self.ready()
        self.dialog.consent_box.setChecked(True)
        self.dialog.save_button.click()
        self.wait(lambda: not self.dialog._active)
        self.dialog.check_button.click()
        self.wait(entered.is_set)
        self.dialog.close()
        self.assertTrue(self.dialog.isVisible())
        self.wait(lambda: not self.dialog.isVisible())
        self.assertIsNone(self.session.history)

    def test_narrow_dialog_wraps_consent_and_has_no_default_save(self):
        self.dialog.resize(480, 620)
        self.app.processEvents()
        self.assertLessEqual(self.dialog.minimumSizeHint().width(), 480)
        self.assertTrue(self.dialog.consent_description.wordWrap())
        self.assertEqual(self.dialog.consent_box.accessibleDescription(), self.dialog.consent_description.text())
        self.assertFalse(self.dialog.save_button.autoDefault())
        self.assertFalse(self.dialog.save_button.isDefault())

    def test_expiry_unchecks_and_disables_consent(self):
        self.ready()
        self.dialog.consent_box.setChecked(True)
        self.session.clock = lambda: fixture.NOW + timedelta(minutes=5)
        self.wait(lambda: self.session.state == 'expired')
        self.assertFalse(self.dialog.consent_box.isChecked())
        self.assertFalse(self.dialog.save_button.isEnabled())
        self.assertEqual(self.dialog.details.toPlainText(), '')

    def test_save_failure_is_terminal_without_exception_text(self):
        def fail(*args, **kwargs):
            raise RuntimeError('private-sentinel')
        self.client.approve = fail
        self.ready()
        self.dialog.consent_box.setChecked(True)
        self.dialog.save_button.click()
        self.wait(lambda: not self.dialog._active)
        self.assertEqual(self.session.state, 'failed')
        self.assertNotIn('private-sentinel', self.dialog.status.text())
        self.assertFalse(self.dialog.load_button.isEnabled())
        self.assertFalse(self.dialog.save_button.isEnabled())

    def test_close_and_escape_wait_for_worker_and_discard_late_success(self):
        from PySide6.QtCore import QTimer
        for via_escape in (False, True):
            if via_escape:
                self.setUp()
            def slow(backup_id, token):
                time.sleep(.25)
                return self.selection
            self.client.preview = slow
            self.dialog.load_button.click()
            ticks = []
            timer = QTimer()
            timer.setInterval(10)
            timer.timeout.connect(lambda: ticks.append(1))
            timer.start()
            if via_escape:
                from PySide6.QtCore import QEvent, Qt
                from PySide6.QtGui import QKeyEvent
                self.app.sendEvent(self.dialog, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
            else:
                self.dialog.close()
            self.assertTrue(self.dialog.isVisible())
            self.assertFalse(self.dialog.close_button.isEnabled())
            self.wait(lambda: not self.dialog.isVisible())
            timer.stop()
            # Cancellation before worker start is also safe; force-start test below covers responsiveness.
            self.assertIsNone(self.session.receipt)
            self.assertIsNone(self.session.selection)

    def test_close_during_running_save_keeps_event_loop_responsive(self):
        import threading
        from PySide6.QtCore import QTimer
        entered = threading.Event()
        original = self.client.approve
        def slow(*args, **kwargs):
            entered.set()
            time.sleep(.3)
            return original(*args, **kwargs)
        self.client.approve = slow
        self.ready()
        self.dialog.consent_box.setChecked(True)
        self.dialog.save_button.click()
        self.wait(entered.is_set)
        ticks = []
        timer = QTimer()
        timer.setInterval(10)
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start()
        self.dialog.reject()
        self.assertTrue(self.dialog.isVisible())
        self.wait(lambda: not self.dialog.isVisible())
        timer.stop()
        self.assertGreaterEqual(len(ticks), 10)
        self.assertIsNone(self.session.receipt)
