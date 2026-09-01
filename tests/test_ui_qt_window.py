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
            "selected-host",
            "start-diagnosis",
            "cancel-operation",
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


if __name__ == "__main__":
    unittest.main()
