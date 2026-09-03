from __future__ import annotations

import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.application.restore_preflight import PrepareLocalRestore
from llm_manager.application.restore_preview import CreateRestoreApproval, CreateRestorePreview
from llm_manager.domain.enums import ChangeOperation
from llm_manager.domain.models import Change, ChangeSet, EncryptionInfo
from llm_manager.infrastructure.backup import LocalBackupStore


class RestorePreflightTests(unittest.TestCase):
    def _fixture(self, root: Path):
        target_root = root / "config"
        target_root.mkdir()
        target = target_root / "opencode.json"
        target.write_text("old", encoding="utf-8")
        before = hashlib.sha256(b"old").hexdigest()
        change = Change(
            "change", str(target), ChangeOperation.REPLACE_FILE, "old", "new",
            before, "masked", source_span=(0, 3), replacement_text="new",
        )
        changes = ChangeSet("changes", "local:test", (change,), "c" * 64)
        store = LocalBackupStore(root / "backups", (target_root,))
        manifest = store.create(BackupRequest(
            "backup-1", "plan-1", "local:test", None, changes,
            EncryptionInfo(enabled=False),
        ), CancellationToken())
        preview = CreateRestorePreview().execute(manifest)
        approval = CreateRestoreApproval().execute(
            preview, "restore-approval-1", "tester", True
        )
        return store, manifest, preview, approval

    def test_reloads_strict_manifest_and_returns_bound_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, manifest, preview, approval = self._fixture(Path(directory))
            prepared = PrepareLocalRestore(store).execute(
                "local:test", "backup-1", preview, approval, CancellationToken()
            )
            self.assertEqual(prepared.manifest_hash, manifest.manifest_hash)
            self.assertEqual(prepared.preview_hash, preview.preview_hash)
            self.assertEqual(prepared.approval_id, approval.approval_id)
            self.assertEqual(prepared.targets, tuple(item.target for item in manifest.items))
            self.assertEqual(prepared.with_hash(), prepared)

    def test_rejects_changed_preview_and_manifest_before_content_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, manifest, preview, approval = self._fixture(Path(directory))
            changed = replace(preview, protected=not preview.protected, preview_hash="").with_hash()
            rebound = CreateRestoreApproval().execute(
                changed, "restore-approval-2", "tester", True
            )
            with self.assertRaises(AdapterError) as caught:
                PrepareLocalRestore(store).execute(
                    "local:test", "backup-1", changed, rebound, CancellationToken()
                )
            self.assertEqual(caught.exception.code, "restore_binding_mismatch")
            Path(manifest.storage_location, "manifest.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(AdapterError):
                PrepareLocalRestore(store).execute(
                    "local:test", "backup-1", preview, approval, CancellationToken()
                )

    def test_rejects_mismatched_approval_and_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, _manifest, preview, approval = self._fixture(Path(directory))
            with self.assertRaises(AdapterError) as caught:
                PrepareLocalRestore(store).execute(
                    "local:test", "backup-1", preview,
                    replace(approval, backup_id="backup-2"), CancellationToken(),
                )
            self.assertEqual(caught.exception.code, "invalid_restore_approval")
            cancellation = CancellationToken()
            cancellation.cancel()
            with self.assertRaises(OperationCancelled):
                PrepareLocalRestore(store).execute(
                    "local:test", "backup-1", preview, approval, cancellation
                )


if __name__ == "__main__":
    unittest.main()
