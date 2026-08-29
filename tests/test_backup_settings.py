import tempfile
import unittest
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.domain.models import EncryptionInfo
from llm_manager.infrastructure.backup_settings import BackupSettingsStore, BuildMode, default_backup_policy


class BackupSettingsTests(unittest.TestCase):
    def test_build_mode_only_controls_initial_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = BackupSettingsStore(Path(directory) / "settings" / "backup.json")
            self.assertFalse(store.load(BuildMode.DEVELOPMENT).enabled)
            self.assertTrue(store.load(BuildMode.DISTRIBUTION).enabled)
            store.save(EncryptionInfo(enabled=False))
            self.assertFalse(store.load(BuildMode.DISTRIBUTION).enabled)

    def test_saved_enabled_policy_is_canonical_and_private(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings" / "backup.json"
            store = BackupSettingsStore(path)
            policy = default_backup_policy(BuildMode.DISTRIBUTION)
            store.save(policy)
            self.assertEqual(store.load(BuildMode.DEVELOPMENT), policy)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_rejects_symlink_and_noncanonical_or_unknown_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            real = base / "real.json"
            real.write_text('{}', encoding="utf-8")
            link = base / "backup.json"
            link.symlink_to(real)
            with self.assertRaises(AdapterError):
                BackupSettingsStore(link).load(BuildMode.DEVELOPMENT)
            link.unlink()
            link.write_text('{"schema_version":"1.0","encryption_enabled":false,"extra":1}', encoding="utf-8")
            with self.assertRaises(AdapterError):
                BackupSettingsStore(link).load(BuildMode.DEVELOPMENT)


if __name__ == "__main__":
    unittest.main()
