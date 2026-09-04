import unittest
from unittest.mock import MagicMock, patch

from llm_manager.application.apply_availability import ApplyRoute
from llm_manager.domain.models import EncryptionInfo
from llm_manager.ui import qt_app


class QtProductionCompositionTests(unittest.TestCase):
    def test_main_exposes_only_local_user_apply_and_restore_routes(self) -> None:
        hosts = (MagicMock(),)
        diagnostic_tasks = MagicMock()
        change_tasks = MagicMock()
        apply_tasks = MagicMock()
        inventory_tasks = MagicMock()
        restore_tasks = MagicMock()
        backup_policy = EncryptionInfo(enabled=False)
        with patch.object(qt_app, "DiscoverHosts") as discover, patch.object(
            qt_app.DiagnosticTaskFactory, "production", return_value=diagnostic_tasks
        ), patch.object(qt_app, "ChangePlanTaskFactory", return_value=change_tasks), patch.object(
            qt_app.LocalUserApplyTaskFactory, "production", return_value=apply_tasks
        ), patch.object(
            qt_app.LocalBackupInventoryTaskFactory,
            "production",
            return_value=inventory_tasks,
        ), patch.object(
            qt_app.LocalUserRestoreTaskFactory,
            "production",
            return_value=restore_tasks,
        ), patch.object(
            qt_app.BackupSettingsStore, "load", return_value=backup_policy
        ), patch.object(qt_app, "run_gui", return_value=0) as run_gui:
            discover.return_value.execute.return_value = hosts

            self.assertEqual(qt_app.main(("llm-manager",)), 0)

        keywords = run_gui.call_args.kwargs
        self.assertIs(keywords["apply_task_factory"], apply_tasks)
        service = keywords["apply_availability_service"]
        self.assertEqual(service.available_routes, frozenset({ApplyRoute.LOCAL_USER}))
        self.assertIs(keywords["change_plan_task_factory"], change_tasks)
        self.assertIs(keywords["backup_inventory_task_factory"], inventory_tasks)
        self.assertIs(keywords["restore_preview_task_factory"], inventory_tasks.preview)
        self.assertIs(keywords["restore_task_factory"], restore_tasks.task)


if __name__ == "__main__":
    unittest.main()
