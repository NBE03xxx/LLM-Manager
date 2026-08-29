import unittest

from llm_manager.adapters.fakes import (
    FakeAuditAdapter,
    FakeBackupStore,
    FakeClientAdapter,
    FakeHostAdapter,
    FakeOllamaAdapter,
    FakePrivilegeAdapter,
)
from llm_manager.application.ports import (
    AuditPort,
    BackupStorePort,
    BackupRequest,
    CancellationToken,
    ClientAdapter,
    CommandRequest,
    CommandResult,
    HostPort,
    OllamaPort,
    PrivilegePort,
)
from llm_manager.domain.models import HostCapabilities, OllamaInfo, OpenCodeInfo

from tests.fixtures import change_set, host_info, manifest


class PortContractTests(unittest.TestCase):
    def test_fakes_satisfy_runtime_protocols(self) -> None:
        host = FakeHostAdapter(host_info())
        ollama = FakeOllamaAdapter(OllamaInfo(installed=False))
        client = FakeClientAdapter(OpenCodeInfo(installed=False))
        backup = FakeBackupStore(manifest())
        privilege = FakePrivilegeAdapter(HostCapabilities(can_elevate=True))
        audit = FakeAuditAdapter()
        self.assertIsInstance(host, HostPort)
        self.assertIsInstance(ollama, OllamaPort)
        self.assertIsInstance(client, ClientAdapter)
        self.assertIsInstance(backup, BackupStorePort)
        self.assertIsInstance(privilege, PrivilegePort)
        self.assertIsInstance(audit, AuditPort)

    def test_command_request_rejects_empty_argv(self) -> None:
        with self.assertRaises(ValueError):
            CommandRequest((), 1000, "correlation")

    def test_fake_host_records_readonly_execution(self) -> None:
        result = CommandResult(("uname",), 0, "Linux", "", False, 1)
        host = FakeHostAdapter(host_info(), command_results={("uname",): result})
        request = CommandRequest(("uname",), 1000, "correlation")
        self.assertEqual(host.execute_readonly(request, CancellationToken()), result)
        self.assertEqual(host.calls[-1][0], "execute_readonly")

    def test_fake_backup_store_filters_by_host(self) -> None:
        backup = FakeBackupStore(manifest())
        backup.create(
            BackupRequest("backup-1", "plan-1", "host-1", None, change_set()),
            CancellationToken(),
        )
        self.assertEqual(len(backup.list_manifests("host-1")), 1)
        self.assertEqual(len(backup.list_manifests("other")), 0)
        self.assertTrue(backup.set_protected("host-1", "backup-1", True).protected)


if __name__ == "__main__":
    unittest.main()
