"""Final root restore consent dialog; production menu entry remains disabled."""
from .i18n import Catalog
from .qt_worker import PYSIDE_AVAILABLE, QtTaskRunner, QtUnavailableError, QtWorkerCoordinator

if not PYSIDE_AVAILABLE:
    class RootRestoreExecutionDialog:
        def __init__(self, *args, **kwargs):
            raise QtUnavailableError('pyside6_unavailable')
else:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QCheckBox, QDialog, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

    class RootRestoreExecutionDialog(QDialog):
        def __init__(self, session, *, locale='en', parent=None, coordinator=None):
            super().__init__(parent)
            self.session = session
            self.catalog = Catalog(locale)
            self.coordinator = coordinator or QtWorkerCoordinator()
            self._active = False
            self._closing = False
            self._runner = None
            self._phase = None
            self.setModal(True)
            self.setWindowTitle(self.catalog.text('root_execute.title'))
            self.resize(680, 640)
            layout = QVBoxLayout(self)
            notice = QLabel(self.catalog.text('root_execute.notice'))
            notice.setTextFormat(Qt.TextFormat.PlainText)
            notice.setWordWrap(True)
            layout.addWidget(notice)
            self.details = QPlainTextEdit()
            self.details.setReadOnly(True)
            self.details.setObjectName('root-execute-details')
            self.details.setAccessibleName(self.catalog.text('root_execute.title'))
            layout.addWidget(self.details)
            self.status = QLabel()
            self.status.setTextFormat(Qt.TextFormat.PlainText)
            self.status.setWordWrap(True)
            self.status.setObjectName('root-execute-status')
            layout.addWidget(self.status)
            self.consent_description = QLabel(self.catalog.text('root_execute.consent'))
            self.consent_description.setTextFormat(Qt.TextFormat.PlainText)
            self.consent_description.setWordWrap(True)
            layout.addWidget(self.consent_description)
            self.consent_box = QCheckBox(self.catalog.text('root_execute.agree'))
            self.consent_box.setAccessibleDescription(self.consent_description.text())
            self.execute_button = QPushButton(self.catalog.text('root_execute.run'))
            self.check_button = QPushButton(self.catalog.text('root_execute.check'))
            self.close_button = QPushButton(self.catalog.text('root_execute.close'))
            for control, name in ((self.consent_box, 'root-execute-consent'),
                                  (self.execute_button, 'root-execute-run'),
                                  (self.check_button, 'root-execute-check'),
                                  (self.close_button, 'root-execute-close')):
                control.setObjectName(name)
                control.setAccessibleName(control.text())
                layout.addWidget(control)
                if isinstance(control, QPushButton):
                    control.setAutoDefault(False)
                    control.setDefault(False)
            self.consent_box.toggled.connect(self._consent)
            self.execute_button.clicked.connect(self._execute)
            self.check_button.clicked.connect(self._check)
            self.close_button.clicked.connect(self.reject)
            self._timer = QTimer(self)
            self._timer.setInterval(200)
            self._timer.timeout.connect(self._render)
            self._timer.start()
            self._render()

        def _consent(self, checked):
            try: self.session.consent(checked)
            except Exception: self.session.fail()
            self._render()

        def _execute(self):
            if self._active or self._closing or not self.session.can_execute: return
            try: task = self.session.execute_task()
            except Exception:
                self.session.fail()
                self._render()
                return
            self._start(task, 'executing')

        def _check(self):
            if self._active or self._closing or not self.session.can_check_status: return
            self._start(self.session.status_task(), 'checking')

        def _start(self, task, phase):
            self._phase = phase
            runner = QtTaskRunner(task)
            self._runner = runner
            runner.signals.result.connect(self._result)
            runner.signals.error.connect(self._failed)
            runner.signals.cancelled.connect(self._failed)
            runner.signals.finished.connect(self._finished)
            self._active = True
            try: self.coordinator.start('root-execute', runner)
            except Exception:
                self._active = False
                self.session.worker_failed(phase)
            self._render()

        def _result(self, value):
            if self._closing: return
            try:
                if self._phase == 'executing': self.session.receive_execution(value)
                else: self.session.receive_status(value)
            except Exception:
                self.session.worker_failed(self._phase)
            self._render()

        def _failed(self, *_args):
            self.session.worker_failed(self._phase)
            self._render()

        def _finished(self):
            self._active = False
            self._runner = None
            if self._closing:
                self._timer.stop()
                super().reject()
            else: self._render()

        def _file_text(self, state):
            if not state.exists: return self.catalog.text('root_execute.absent')
            return self.catalog.text('root_execute.file', digest=state.sha256,
                                     mode=f'{state.mode:04o}', uid=state.uid, gid=state.gid)

        def _render(self):
            self.session.expire()
            request = self.session.request
            content = self.catalog.text(
                'root_execute.metadata', host=request.host_id, uid=request.caller_uid,
                backup=request.backup_id, target=request.target, expires=request.expires_at.isoformat(),
                current=self._file_text(request.current), original=self._file_text(request.backup),
                digest=request.request_hash,
            )
            if self.details.toPlainText() != content: self.details.setPlainText(content)
            state = self.session.state
            key = 'root_execute.' + state
            if state == 'checked':
                history = self.session.history
                outcome = history.result.state.value if history.result is not None else (
                    'unknown' if history.attempt is not None else 'review_only')
                key = 'root_execute.history_' + outcome
            self.status.setText(self.catalog.text('root_execute.closing' if self._closing else key))
            self.status.setAccessibleName(self.status.text())
            self.consent_box.setEnabled(state == 'ready' and not self._active and not self._closing)
            self.consent_box.blockSignals(True)
            self.consent_box.setChecked(self.session.can_execute)
            self.consent_box.blockSignals(False)
            self.execute_button.setEnabled(self.session.can_execute and not self._active and not self._closing)
            self.check_button.setEnabled(self.session.can_check_status and not self._active and not self._closing)
            self.close_button.setEnabled(not self._closing)

        def done(self, result):
            if self._active:
                self._closing = True
                self.session.worker_failed(self._phase)
                if self._runner is not None: self._runner.cancel()
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
