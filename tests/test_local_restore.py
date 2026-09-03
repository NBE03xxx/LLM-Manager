from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.application.restore_preflight import PrepareLocalRestore
from llm_manager.application.restore_preview import CreateRestoreApproval, CreateRestorePreview
from llm_manager.infrastructure.local_restore import (
    LocalRestoreState,
    SingleTargetLocalRestoreExecutor,
)
from tests.test_restore_preflight import _fixture


class LocalRestoreExecutorTests(unittest.TestCase):
    def test_single_target_restore_is_atomic_and_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, manifest, preview, approval = _fixture(Path(directory))
            target = Path(manifest.items[0].target)
            target.write_text("new", encoding="utf-8")
            preview = CreateRestorePreview().execute(manifest)
            approval = CreateRestoreApproval().execute(preview, "approval-2", "tester", True)
            authorization = PrepareLocalRestore(store).execute(
                manifest.host_id, manifest.backup_id, preview, approval, CancellationToken()
            )
            result = SingleTargetLocalRestoreExecutor(store).execute(
                authorization, CancellationToken()
            )
            self.assertEqual(result.state, LocalRestoreState.COMMITTED)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")

    def test_changed_target_and_authorization_fail_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, manifest, preview, approval = _fixture(Path(directory))
            authorization = PrepareLocalRestore(store).execute(
                manifest.host_id, manifest.backup_id, preview, approval, CancellationToken()
            )
            target = Path(manifest.items[0].target)
            target.write_text("changed", encoding="utf-8")
            with self.assertRaises(AdapterError) as caught:
                SingleTargetLocalRestoreExecutor(store).execute(
                    authorization, CancellationToken()
                )
            self.assertEqual(caught.exception.code, "stale_restore_target")
            self.assertEqual(target.read_text(encoding="utf-8"), "changed")
            with self.assertRaises(AdapterError) as caught:
                SingleTargetLocalRestoreExecutor(store).execute(
                    replace(authorization, manifest_hash="0" * 64), CancellationToken()
                )
            self.assertEqual(caught.exception.code, "invalid_restore_authorization")

    def test_multiple_targets_are_rejected_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, manifest, preview, approval = _fixture(Path(directory))
            authorization = PrepareLocalRestore(store).execute(
                manifest.host_id, manifest.backup_id, preview, approval, CancellationToken()
            )
            target = Path(manifest.items[0].target)
            expanded = replace(
                authorization,
                targets=authorization.targets + (str(target.parent / "second.json"),),
                authorization_hash="",
            ).with_hash()
            with self.assertRaises(AdapterError) as caught:
                SingleTargetLocalRestoreExecutor(store).execute(expanded, CancellationToken())
            self.assertEqual(caught.exception.code, "invalid_restore_authorization")
            self.assertEqual(target.read_text(encoding="utf-8"), "old")


if __name__ == "__main__":
    unittest.main()
