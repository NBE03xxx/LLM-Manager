from __future__ import annotations

import hashlib
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.application.restore_preview import CreateRestoreApproval
from llm_manager.domain.enums import ChangeOperation
from llm_manager.domain.models import Change, ChangeSet, EncryptionInfo, utc_now
from llm_manager.infrastructure.backup import LocalBackupStore
from llm_manager.infrastructure.journal import LocalOperationJournal
from llm_manager.infrastructure.local_apply_inventory import LocalApplyInventoryService


class RestorePreviewTests(unittest.TestCase):
    def _service(self, root: Path) -> LocalApplyInventoryService:
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
        backups = LocalBackupStore(root / "backups", (target_root,))
        backups.create(BackupRequest(
            "backup-1", "plan-1", "local:test", None, changes,
            EncryptionInfo(enabled=False),
        ), CancellationToken())
        return LocalApplyInventoryService(
            backups, LocalOperationJournal(root / "journal", (target_root,))
        )

    def test_preview_uses_manifest_metadata_without_restore_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            preview = self._service(Path(directory)).preview_restore(
                "local:test", "backup-1", CancellationToken()
            )
            self.assertEqual(preview.backup_id, "backup-1")
            self.assertEqual(len(preview.items), 1)
            self.assertTrue(preview.items[0].existed)
            self.assertEqual(preview.items[0].sha256, hashlib.sha256(b"old").hexdigest())
            self.assertFalse(hasattr(preview.items[0], "content"))

    def test_approval_requires_explicit_current_exact_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            preview = self._service(Path(directory)).preview_restore(
                "local:test", "backup-1", CancellationToken()
            )
            service = CreateRestoreApproval()
            with self.assertRaises(AdapterError) as caught:
                service.execute(preview, "approval-1", "tester", False)
            self.assertEqual(caught.exception.code, "explicit_restore_review_required")
            approval = service.execute(preview, "approval-1", "tester", True)
            self.assertTrue(approval.is_valid_for(preview))
            self.assertFalse(approval.is_valid_for(replace(preview, backup_id="backup-2")))

    def test_tampered_or_expired_preview_cannot_be_approved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            preview = self._service(Path(directory)).preview_restore(
                "local:test", "backup-1", CancellationToken()
            )
            with self.assertRaises(AdapterError) as caught:
                CreateRestoreApproval().execute(
                    replace(preview, manifest_hash="0" * 64), "approval-1", "tester", True
                )
            self.assertEqual(caught.exception.code, "stale_restore_preview")
            with self.assertRaises(AdapterError) as caught:
                CreateRestoreApproval().execute(
                    preview, "approval-1", "tester", True,
                    now=preview.expires_at + timedelta(seconds=1),
                )
            self.assertEqual(caught.exception.code, "stale_restore_preview")


if __name__ == "__main__":
    unittest.main()
