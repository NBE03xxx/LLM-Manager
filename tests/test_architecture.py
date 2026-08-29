import ast
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src" / "llm_manager"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


class ArchitectureTests(unittest.TestCase):
    def test_domain_does_not_import_framework_or_io_modules(self) -> None:
        forbidden = ("PySide6", "subprocess", "socket", "requests", "httpx", "paramiko")
        for path in (SRC_ROOT / "domain").glob("*.py"):
            for module in imported_modules(path):
                self.assertFalse(module.startswith(forbidden), f"{path} imports forbidden {module}")

    def test_domain_does_not_depend_on_outer_project_layers(self) -> None:
        forbidden = ("llm_manager.ui", "llm_manager.application", "llm_manager.adapters", "llm_manager.infrastructure")
        for path in (SRC_ROOT / "domain").glob("*.py"):
            for module in imported_modules(path):
                self.assertFalse(module.startswith(forbidden), f"{path} imports outer layer {module}")

    def test_ui_is_not_created_during_phase_one(self) -> None:
        self.assertFalse((SRC_ROOT / "ui").exists())

    def test_optimization_and_planning_do_not_depend_on_ui_or_concrete_adapters(self) -> None:
        forbidden = ("PySide6", "llm_manager.ui", "llm_manager.adapters", "llm_manager.infrastructure")
        for directory in ("optimization", "planning"):
            for path in (SRC_ROOT / directory).glob("*.py"):
                for module in imported_modules(path):
                    self.assertFalse(module.startswith(forbidden), f"{path} imports outer layer {module}")


if __name__ == "__main__":
    unittest.main()
