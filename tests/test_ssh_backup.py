from __future__ import annotations

import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import BackupRequest, CancellationToken, FileStat
from llm_manager.domain.enums import ChangeOperation, HostKind
from llm_manager.domain.models import (
    Change, ChangeSet, EncryptionInfo, HostCapabilities, HostInfo,
)
from llm_manager.infrastructure.backup import LocalBackupStore
from llm_manager.infrastructure.ssh_backup import SshSnapshotLocalBackupStore


TARGET = "/home/remote/.config/opencode/opencode.jsonc"
CONTENT = b'{"model":"old"}\n'
DIGEST = hashlib.sha256(CONTENT).hexdigest()


class SshSnapshotLocalBackupStoreTests(unittest.TestCase):
    def test_captures_stable_remote_content_into_verified_local_authoritative_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            host = _Host()
            store = _store(Path(directory), host)
            manifest = store.create(_request(), CancellationToken())

            self.assertEqual([call[0] for call in host.calls], ["identify", "stat", "read", "stat"])
            self.assertTrue(all(result.status.value == "passed" for result in store.verify(manifest, CancellationToken())))
            restored = store.restore_items(manifest, CancellationToken())
            self.assertEqual(restored[0].content, CONTENT)
            self.assertEqual(restored[0].sha256, DIGEST)

    def test_rejects_host_target_and_snapshot_change_before_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrong_host = _Host(identity=replace(_Host().identity, fingerprint="SHA256:other"))
            with self.assertRaises(AdapterError) as identity_error:
                _store(root / "identity", wrong_host).create(_request(), CancellationToken())
            self.assertEqual(identity_error.exception.code, "host_identity_changed")

            with self.assertRaises(AdapterError) as target_error:
                _store(root / "target", _Host()).create(
                    _request(target="/home/remote/.ssh/authorized_keys"), CancellationToken()
                )
            self.assertEqual(target_error.exception.code, "ssh_backup_target_not_allowed")

            changed = _Host(change_after_read=True)
            with self.assertRaises(AdapterError) as snapshot_error:
                _store(root / "changed", changed).create(_request(), CancellationToken())
            self.assertEqual(snapshot_error.exception.code, "ssh_backup_snapshot_changed")
            self.assertFalse((root / "changed" / "backups").exists())

    def test_captured_store_rejects_change_set_before_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = _request(before_hash="f" * 64)
            with self.assertRaises(AdapterError) as error:
                _store(Path(directory), _Host()).create(request, CancellationToken())
            self.assertEqual(error.exception.code, "captured_backup_mismatch")


class _Host:
    def __init__(self, *, identity=None, change_after_read=False):
        self.identity = identity or HostInfo(
            "ssh-host", HostKind.SSH, "Remote", HostCapabilities(),
            ssh_alias="remote", fingerprint="SHA256:verified",
        )
        self.change_after_read = change_after_read
        self.calls = []
        self.read = False

    def identify(self, cancellation):
        self.calls.append(("identify",))
        return self.identity

    def capabilities(self):
        return HostCapabilities()

    def execute_readonly(self, request, cancellation):
        raise AssertionError("unexpected command")

    def stat(self, path, cancellation):
        self.calls.append(("stat", path))
        digest = "e" * 64 if self.change_after_read and self.read else DIGEST
        return FileStat(path, True, digest, 0o600, 1000, 1000, False)

    def read_file(self, path, max_bytes, cancellation):
        self.calls.append(("read", path, max_bytes))
        self.read = True
        return CONTENT


def _store(root: Path, host: _Host) -> SshSnapshotLocalBackupStore:
    target_root = Path("/home/remote/.config/opencode")
    return SshSnapshotLocalBackupStore(
        LocalBackupStore(root / "backups", (target_root,)), host, frozenset({TARGET})
    )


def _request(*, target: str = TARGET, before_hash: str | None = DIGEST) -> BackupRequest:
    change_set = ChangeSet(
        "changes", "ssh-host",
        (Change("change-1", target, ChangeOperation.REPLACE_FILE, "old", "new", before_hash, "diff"),),
        "change-set-hash",
    )
    return BackupRequest(
        "backup-1", "plan-1", "ssh-host", "SHA256:verified", change_set,
        EncryptionInfo(enabled=False),
    )


if __name__ == "__main__":
    unittest.main()
