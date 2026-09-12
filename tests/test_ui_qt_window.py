import ast
import unittest
from pathlib import Path

from llm_manager.ui.qt_worker import PYSIDE_AVAILABLE, QtUnavailableError
from llm_manager.ui.qt_window import MainWindow


QT_WINDOW = Path(__file__).resolve().parents[1] / "src" / "llm_manager" / "ui" / "qt_window.py"


class QtWindowBoundaryTests(unittest.TestCase):
    def test_missing_pyside_window_fails_with_stable_error(self) -> None:
        if PYSIDE_AVAILABLE:
            self.skipTest("PySide6 is available in this environment")
        with self.assertRaisesRegex(QtUnavailableError, "pyside6_unavailable"):
            MainWindow(object())

    def test_window_declares_accessible_names_for_primary_controls(self) -> None:
        source = QT_WINDOW.read_text(encoding="utf-8")
        for name in (
            "workflow-navigation",
            "workflow-status",
            "language-selector",
            "host-selector",
            "selected-host",
            "start-diagnosis",
            "cancel-operation",
            "profile-selector",
            "recommendation-summary",
            "recommendation-list",
            "review-selected",
            "review-summary",
            "review-list",
            "backup-inventory-summary",
            "backup-inventory-list",
            "refresh-backup-inventory",
            "restore-preview-summary",
            "restore-preview-list",
            "approve-restore-preview",
            "restore-approval-status",
        ):
            self.assertIn(f'"{name}"', source)

    def test_window_has_no_process_network_or_privilege_imports(self) -> None:
        tree = ast.parse(QT_WINDOW.read_text(encoding="utf-8"))
        forbidden = ("subprocess", "socket", "requests", "paramiko", "llm_manager.infrastructure")
        modules = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        ]
        modules.extend(
            alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
        )
        self.assertFalse(any(module.startswith(forbidden) for module in modules))

    def test_pages_are_scrollable_and_close_waits_for_workers(self) -> None:
        source = QT_WINDOW.read_text(encoding="utf-8")
        self.assertIn("QScrollArea", source)
        self.assertIn("scroll.setWidgetResizable(True)", source)
        self.assertIn("label.setWordWrap(True)", source)
        self.assertIn("def closeEvent", source)
        self.assertIn("self._coordinator.cancel(host_id)", source)
        self.assertIn("QTimer.singleShot(0, self.close)", source)
        self.assertIn('"status.closing_wait" if self._close_pending', source)
        self.assertIn("remaining_ms = max(1, int(remaining_seconds * 1000))", source)

    def test_accessible_names_follow_localized_visible_text(self) -> None:
        source = QT_WINDOW.read_text(encoding="utf-8")
        self.assertIn("def _refresh_accessible_names", source)
        self.assertIn("widget.setAccessibleName(widget.text())", source)
        self.assertIn("label.setAccessibleName(label.text())", source)
        self.assertIn("self._host_label.setBuddy(self._host_selector)", source)
        self.assertIn("self._language_label.setBuddy(self._language)", source)
        self.assertIn("self._profile_label.setBuddy(self._profile_selector)", source)
        self.assertIn("setAccessibleDescription", source)

    def test_root_restore_entry_is_guarded_by_separate_root_availability_check(self) -> None:
        source = QT_WINDOW.read_text(encoding="utf-8")
        self.assertIn('setObjectName("open-root-restore")', source)
        self.assertIn("self._root_restore_route_unavailable() is not None", source)
        self.assertIn("service.execute(host.kind, True)", source)


if __name__ == "__main__":
    unittest.main()
