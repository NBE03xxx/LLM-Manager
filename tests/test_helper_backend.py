import tempfile
import unittest
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure.helper_backend import LocalSystemHelperBackend, SYSTEMCTL
from llm_manager.planning.ollama import DROP_IN_PATH


class LocalSystemHelperBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "etc/systemd/system").mkdir(parents=True)
        self.commands: list[tuple[str, ...]] = []
        self.backend = LocalSystemHelperBackend(
            root=self.root,
            service_runner=lambda argv: self.commands.append(argv) or 0,
            sandbox=True,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_atomic_write_read_remove_and_permissions(self) -> None:
        content = b'[Service]\nEnvironment="OLLAMA_HOST=127.0.0.1:11434"\n'
        self.assertIsNone(self.backend.read_file(DROP_IN_PATH))
        self.backend.atomic_write(DROP_IN_PATH, content, 0o644, 0, 0)
        target = self.root / DROP_IN_PATH.removeprefix("/")
        self.assertEqual(self.backend.read_file(DROP_IN_PATH), content)
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)
        self.backend.remove_file(DROP_IN_PATH)
        self.assertFalse(target.exists())

    def test_uses_only_fixed_systemctl_argv(self) -> None:
        self.backend.daemon_reload()
        self.backend.restart_unit("ollama.service")
        self.assertEqual(
            self.commands,
            [(SYSTEMCTL, "daemon-reload"), (SYSTEMCTL, "restart", "ollama.service")],
        )
        with self.assertRaises(AdapterError):
            self.backend.restart_unit("ssh.service")

    def test_rejects_path_metadata_symlink_and_failed_service(self) -> None:
        with self.assertRaises(AdapterError):
            self.backend.read_file("/etc/passwd")
        with self.assertRaises(AdapterError):
            self.backend.atomic_write(DROP_IN_PATH, b"x", 0o666, 0, 0)
        drop_in_directory = self.root / "etc/systemd/system/ollama.service.d"
        outside = self.root / "outside"
        outside.mkdir()
        drop_in_directory.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(AdapterError):
            self.backend.atomic_write(DROP_IN_PATH, b"x", 0o644, 0, 0)

        failing = LocalSystemHelperBackend(root=self.root, service_runner=lambda argv: 1, sandbox=True)
        with self.assertRaises(AdapterError):
            failing.daemon_reload()

    def test_alternate_root_requires_explicit_sandbox(self) -> None:
        with self.assertRaises(ValueError):
            LocalSystemHelperBackend(root=self.root)


if __name__ == "__main__":
    unittest.main()
