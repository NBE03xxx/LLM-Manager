"""Review-only dialog; explicit consent and asynchronous dedicated client calls."""
from .i18n import Catalog
from .qt_worker import PYSIDE_AVAILABLE, QtTaskRunner, QtUnavailableError, QtWorkerCoordinator

if not PYSIDE_AVAILABLE:
    class RootRestoreReviewDialog:
        def __init__(self, *args, **kwargs):
            raise QtUnavailableError('pyside6_unavailable')
else:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QCheckBox, QDialog, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

    class RootRestoreReviewDialog(QDialog):
        def __init__(self, session, *, locale='en', parent=None, coordinator=None,
                     allow_execution_handoff=False):
            super().__init__(parent)
            self.session = session
            self.catalog = Catalog(locale)
            self.coordinator = coordinator or QtWorkerCoordinator()
            self._active = False
            self._closing = False
            self._runner = None
            self._allow_execution_handoff = allow_execution_handoff is True
            self.setModal(True)
            self.setWindowTitle(self.catalog.text('root_review.title'))
            self.resize(680, 640)
            layout = QVBoxLayout(self)
            notice = QLabel(self.catalog.text('root_review.notice'))
            notice.setTextFormat(Qt.TextFormat.PlainText)
            notice.setWordWrap(True)
            layout.addWidget(notice)
            self.details = QPlainTextEdit()
            self.details.setReadOnly(True)
            self.details.setObjectName('root-review-details')
            self.details.setAccessibleName(self.catalog.text('root_review.title'))
            layout.addWidget(self.details)
            self.status = QLabel()
            self.status.setTextFormat(Qt.TextFormat.PlainText)
            self.status.setWordWrap(True)
            self.status.setObjectName('root-review-status')
            layout.addWidget(self.status)
            self.load_button = QPushButton(self.catalog.text('root_review.load'))
            self.consent_description = QLabel(self.catalog.text('root_review.consent'))
            self.consent_description.setTextFormat(Qt.TextFormat.PlainText)
            self.consent_description.setWordWrap(True)
            layout.addWidget(self.consent_description)
            self.consent_box = QCheckBox(self.catalog.text('root_review.agree'))
            self.consent_box.setAccessibleDescription(self.consent_description.text())
            self.save_button = QPushButton(self.catalog.text('root_review.save'))
            self.check_button = QPushButton(self.catalog.text('root_review.check'))
            self.continue_button = QPushButton(self.catalog.text('root_review.continue'))
            self.close_button = QPushButton(self.catalog.text('root_review.close'))
            for control, name in ((self.load_button, 'root-review-load'),
                                  (self.consent_box, 'root-review-consent'),
                                  (self.save_button, 'root-review-save'),
                                  (self.check_button, 'root-review-check'),
                                  (self.continue_button, 'root-review-continue'),
                                  (self.close_button, 'root-review-close')):
                control.setObjectName(name)
                control.setAccessibleName(control.text())
                layout.addWidget(control)
                if isinstance(control, QPushButton):
                    control.setAutoDefault(False)
                    control.setDefault(False)
            self.load_button.clicked.connect(self._load)
            self.consent_box.toggled.connect(self._consent)
            self.save_button.clicked.connect(self._save)
            self.check_button.clicked.connect(self._check)
            self.continue_button.clicked.connect(self._continue)
            self.close_button.clicked.connect(self.reject)
            self._timer = QTimer(self)
            self._timer.setInterval(200)
            self._timer.timeout.connect(self._render)
            self._timer.start()
            self._render()

        def _load(self):
            if self._active or self.session.state != 'new':
                return
            self._start(self.session.preview_task(), 'loading')

        def _consent(self, checked):
            try:
                self.session.consent(checked)
            except Exception:
                self.session.fail()
            self._render()

        def _save(self):
            if self._active or not self.session.can_save:
                return
            try:
                task = self.session.save_task()
            except Exception:
                self.session.fail()
                self._render()
                return
            self._start(task, 'saving')

        def _check(self):
            if self._active or self._closing or not self.session.can_check_status:
                return
            self._start(self.session.status_task(), 'checking')

        def _continue(self):
            if (not self._active and not self._closing and self._allow_execution_handoff
                    and self.session.state == 'saved'):
                try:
                    self.session.approved_request_for_execution()
                except Exception:
                    self.session.fail()
                    self._render()
                    return
                self.accept()

        def _start(self, task, phase):
            self._phase = phase
            runner = QtTaskRunner(task)
            self._runner = runner
            runner.signals.result.connect(self._result)
            runner.signals.error.connect(self._failed)
            runner.signals.cancelled.connect(self._failed)
            runner.signals.finished.connect(self._finished)
            self._active = True
            try:
                self.coordinator.start('root-review', runner)
            except Exception:
                self._active = False
                self.session.fail()
            self._render()

        def _result(self, value):
            if self._closing:
                return
            try:
                if self._phase == 'loading':
                    self.session.receive_preview(value)
                elif self._phase == 'checking':
                    self.session.receive_status(value)
                else:
                    self.session.receive_receipt(value)
            except Exception:
                self.session.fail('check_failed' if self._phase == 'checking' else 'failed')
            self._render()

        def _failed(self, *_args):
            self.session.fail('check_failed' if self._phase == 'checking' else 'failed')
            self._render()

        def _finished(self):
            self._active = False
            self._runner = None
            if self._closing:
                self._timer.stop()
                super().reject()
            else:
                self._render()

        def _file_text(self, state):
            if not state.exists:
                return self.catalog.text('root_review.absent')
            return self.catalog.text('root_review.file', exists=True, digest=state.sha256,
                                     mode=f'{state.mode:04o}', uid=state.uid, gid=state.gid)

        def _render(self):
            self.session.expire()
            state = self.session.state
            selection = self.session.selection
            if selection is not None:
                content = self.catalog.text('root_review.metadata', host=selection.host_id,
                    uid=selection.caller_uid, backup=selection.backup_id, target=selection.target,
                    expires=selection.expires_at.isoformat(), current=self._file_text(selection.current),
                    original=self._file_text(selection.backup), digest=selection.preview_hash)
            else:
                content = ''
            # Preserve scroll position while polling expiry.
            if self.details.toPlainText() != content:
                self.details.setPlainText(content)
            key = 'root_review.' + state
            if state == 'checked':
                history = self.session.history
                outcome = history.result.state.value if history.result is not None else (
                    'unknown' if history.attempt is not None else 'review_only')
                key = 'root_review.history_' + outcome
            self.status.setText(self.catalog.text('root_review.closing' if self._closing else key))
            self.status.setAccessibleName(self.status.text())
            self.load_button.setEnabled(state == 'new' and not self._active and not self._closing)
            self.consent_box.setEnabled(state == 'ready' and not self._active and not self._closing)
            self.consent_box.blockSignals(True)
            self.consent_box.setChecked(self.session.can_save)
            self.consent_box.blockSignals(False)
            self.save_button.setEnabled(self.session.can_save and not self._active and not self._closing)
            self.check_button.setEnabled(self.session.can_check_status and not self._active and not self._closing)
            self.continue_button.setVisible(self._allow_execution_handoff)
            self.continue_button.setEnabled(self._allow_execution_handoff and state == 'saved'
                                            and not self._active and not self._closing)
            self.close_button.setEnabled(not self._closing)

        def done(self, result):
            # Includes Escape, reject(), accept() and window-manager close paths.
            if self._active:
                self._closing = True
                self.session.fail()
                if self._runner is not None:
                    self._runner.cancel()
                self._render()
                return
            self._timer.stop()
            super().done(result)

        def closeEvent(self, event):
            if self._active:
                self.done(QDialog.DialogCode.Rejected)
                event.ignore()
            else:
                self._timer.stop()
                super().closeEvent(event)
