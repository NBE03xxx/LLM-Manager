import ast
import unittest
from pathlib import Path

from llm_manager.ui.qt_worker import PYSIDE_AVAILABLE, QtUnavailableError, require_pyside6


QT_WORKER = Path(__file__).resolve().parents[1] / "src" / "llm_manager" / "ui" / "qt_worker.py"


class QtWorkerBoundaryTests(unittest.TestCase):
    def test_missing_pyside_is_reported_with_stable_error(self) -> None:
        if PYSIDE_AVAILABLE:
            self.skipTest("PySide6 is available in this environment")
        with self.assertRaisesRegex(QtUnavailableError, "pyside6_unavailable"):
            require_pyside6()

    def test_qt_worker_contract_uses_thread_pool_runnable_and_signals(self) -> None:
        tree = ast.parse(QT_WORKER.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "PySide6.QtCore"
            for alias in node.names
        }
        self.assertTrue({"QObject", "QRunnable", "QThreadPool", "Signal", "Slot"} <= imported)
        runner_methods = [
            {method.name for method in node.body if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))}
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "QtTaskRunner"
        ]
        self.assertTrue(any({"run", "cancel"} <= methods for methods in runner_methods))

    def test_qt_is_confined_to_ui_layer(self) -> None:
        root = QT_WORKER.parents[1]
        offenders = []
        for path in root.rglob("*.py"):
            if path.is_relative_to(root / "ui"):
                continue
            if "PySide6" in path.read_text(encoding="utf-8"):
                offenders.append(path)
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
