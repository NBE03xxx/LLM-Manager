from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher
from llm_manager.infrastructure.remote_keys import RemoteRootKeyProvider


class RemoteRootKeyProviderTests(unittest.TestCase):
    def test_creates_once_reuses_and_encrypts_with_separate_root_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "keys"
            provider = RemoteRootKeyProvider(
                root, sandbox=True, random_bytes=lambda size: b"r" * size
            )
            first = provider.get_key("remote-master-v1", "remote_root")
            second = RemoteRootKeyProvider(root, sandbox=True).get_key(
                "remote-master-v1", "remote_root"
            )
            self.assertEqual(first, second)
            self.assertEqual(first, b"r" * 32)
            path = root / "remote-master-v1.key"
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            envelope = AesGcmBackupCipher(provider, lambda size: b"n" * size).encrypt(
                b"secret", backup_id="backup", host_fingerprint="SHA256:test",
                target="/etc/example", key_reference="remote-master-v1",
                key_scope="remote_root",
            )
            self.assertNotIn(b"secret", envelope)

    def test_rejects_scope_reference_production_alternate_and_nonroot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "keys"
            with self.assertRaises(ValueError):
                RemoteRootKeyProvider(root)
            provider = RemoteRootKeyProvider(root, sandbox=True)
            for reference, scope in (("../escape", "remote_root"), ("key", "local_secret_service")):
                with self.subTest(reference=reference, scope=scope), self.assertRaises(AdapterError):
                    provider.get_key(reference, scope)
            production = RemoteRootKeyProvider(effective_uid=1000)
            with self.assertRaises(AdapterError) as caught:
                production.get_key("remote-master-v1", "remote_root")
            self.assertEqual(caught.exception.code, "root_required")

    def test_rejects_wrong_mode_size_symlink_and_unsafe_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "keys"
            provider = RemoteRootKeyProvider(root, sandbox=True, random_bytes=lambda size: b"k" * size)
            provider.get_key("mode", "remote_root")
            path = root / "mode.key"
            os.chmod(path, 0o644)
            with self.assertRaises(AdapterError):
                provider.get_key("mode", "remote_root")
            bad = root / "short.key"
            bad.write_bytes(b"short")
            os.chmod(bad, 0o600)
            with self.assertRaises(AdapterError):
                provider.get_key("short", "remote_root")
            target = root / "target"
            target.write_bytes(b"x" * 32)
            link = root / "link.key"
            os.symlink(target, link)
            with self.assertRaises(AdapterError):
                provider.get_key("link", "remote_root")
            os.chmod(root, 0o755)
            with self.assertRaises(AdapterError):
                provider.get_key("new", "remote_root")

    def test_invalid_random_source_never_creates_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "keys"
            provider = RemoteRootKeyProvider(
                root, sandbox=True, random_bytes=lambda size: b"short"
            )
            with self.assertRaises(AdapterError):
                provider.get_key("remote-master-v1", "remote_root")
            self.assertFalse((root / "remote-master-v1.key").exists())


if __name__ == "__main__":
    unittest.main()
