"""Root-owned backup inventory dialog; selection has no mutation authority."""
from .i18n import Catalog
from .qt_worker import PYSIDE_AVAILABLE, QtTaskRunner, QtUnavailableError, QtWorkerCoordinator

if not PYSIDE_AVAILABLE:
    class RootRestoreInventoryDialog:
        def __init__(self, *args, **kwargs):
            raise QtUnavailableError('pyside6_unavailable')
else:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog, QLabel, QListWidget, QPushButton, QVBoxLayout

    class RootRestoreInventoryDialog(QDialog):
        def __init__(self, session, *, locale='en', parent=None, coordinator=None):
            super().__init__(parent)
            self.session = session
            self.catalog = Catalog(locale)
            self.coordinator = coordinator or QtWorkerCoordinator()
            self._active = False
            self._closing = False
            self._runner = None
            self.setModal(True)
            self.setWindowTitle(self.catalog.text('root_inventory.title'))
            self.resize(680, 560)
            layout = QVBoxLayout(self)
            notice = QLabel(self.catalog.text('root_inventory.notice'))
            notice.setTextFormat(Qt.TextFormat.PlainText)
            notice.setWordWrap(True)
            layout.addWidget(notice)
            self.status = QLabel()
            self.status.setTextFormat(Qt.TextFormat.PlainText)
            self.status.setWordWrap(True)
            self.status.setObjectName('root-inventory-status')
            self.items = QListWidget()
            self.items.setObjectName('root-inventory-list')
            self.load_button = QPushButton(self.catalog.text('root_inventory.load'))
            self.review_button = QPushButton(self.catalog.text('root_inventory.review'))
            self.close_button = QPushButton(self.catalog.text('root_inventory.close'))
            for widget in (self.status, self.items, self.load_button,
                           self.review_button, self.close_button):
                widget.setAccessibleName(widget.text() if isinstance(widget, QPushButton)
                                         else widget.objectName())
                layout.addWidget(widget)
                if isinstance(widget, QPushButton):
                    widget.setAutoDefault(False)
                    widget.setDefault(False)
            self.load_button.clicked.connect(self._load)
            self.items.currentItemChanged.connect(self._select)
            self.review_button.clicked.connect(self._review)
            self.close_button.clicked.connect(self.reject)
            self._render()

        def _load(self):
            if self._active or self._closing or self.session.state != 'new':
                return
            try:
                task = self.session.list_task()
                runner = QtTaskRunner(task)
                self._runner = runner
                runner.signals.result.connect(self._result)
                runner.signals.error.connect(self._failed)
                runner.signals.cancelled.connect(self._failed)
                runner.signals.finished.connect(self._finished)
                self._active = True
                self.coordinator.start('root-inventory', runner)
            except Exception:
                self._active = False
                self.session.fail()
            self._render()

        def _result(self, value):
            if self._closing:
                return
            try:
                self.session.receive_inventory(value)
            except Exception:
                self.session.fail()
            self._render()

        def _failed(self, *_args):
            self.session.fail()
            self._render()

        def _finished(self):
            self._active = False
            self._runner = None
            if self._closing:
                super().reject()
            else:
                self._render()

        def _select(self, current, _previous):
            self.session.select(current.data(256) if current is not None else None)
            self._render()

        def _review(self):
            if self.session.can_review and not self._active and not self._closing:
                self.accept()

        def _render(self):
            selected = self.session.selected_backup_id
            self.items.blockSignals(True)
            self.items.clear()
            for item in self.session.items:
                state = (self.catalog.text('root_inventory.absent') if not item.original.exists
                         else self.catalog.text('root_inventory.file', digest=item.original.sha256,
                                                mode=f'{item.original.mode:04o}'))
                self.items.addItem(self.catalog.text(
                    'root_inventory.item', backup=item.backup_id,
                    captured=item.captured_at.isoformat(), state=state,
                    digest=item.record_hash,
                ))
                row = self.items.item(self.items.count() - 1)
                row.setData(256, item.backup_id)
                if item.backup_id == selected:
                    self.items.setCurrentItem(row)
            self.items.blockSignals(False)
            key = 'root_inventory.closing' if self._closing else 'root_inventory.' + self.session.state
            self.status.setText(self.catalog.text(key))
            self.status.setAccessibleName(self.status.text())
            self.load_button.setEnabled(self.session.state == 'new' and not self._active and not self._closing)
            self.items.setEnabled(self.session.state == 'ready' and not self._active and not self._closing)
            self.review_button.setEnabled(self.session.can_review and not self._active and not self._closing)
            self.close_button.setEnabled(not self._closing)

        def done(self, result):
            if self._active:
                self._closing = True
                self.session.fail()
                if self._runner is not None:
                    self._runner.cancel()
                self._render()
                return
            super().done(result)

        def closeEvent(self, event):
            if self._active:
                self.done(QDialog.DialogCode.Rejected)
                event.ignore()
            else:
                super().closeEvent(event)
