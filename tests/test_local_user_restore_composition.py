from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
import uuid
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.host_discovery import HostCandidate
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.application.restore_preview import CreateRestoreApproval, CreateRestorePreview
from llm_manager.domain.enums import ChangeOperation, HostKind
from llm_manager.domain.models import Change, ChangeSet, EncryptionInfo
from llm_manager.infrastructure.backup import LocalBackupStore
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher
from llm_manager.infrastructure.restore_execution import RestoreExecutionState, RestoreExecutionStore
from llm_manager.infrastructure.secret_service import SecretServiceKeyProvider, SecretStorageBackend
from llm_manager.ui.composition import LocalUserRestoreTaskFactory


class _TestKeys:
    def get_key(self, _key_reference: str, _key_scope: str) -> bytes:
        return b"k" * 32


class LocalUserRestoreTaskFactoryTests(unittest.TestCase):
    def _fixture(self, root: Path):
        config = root / "config"
        target_root = config / "opencode"
        target_root.mkdir(parents=True)
        target = target_root / "opencode.json"
        target.write_text("old", encoding="utf-8")
        state = root / "state" / "llm-manager"
        state.mkdir(parents=True, mode=0o700)
        state.chmod(0o700)
        change = Change(
            "change", str(target), ChangeOperation.REPLACE_FILE, "old", "new",
            hashlib.sha256(b"old").hexdigest(), "masked", source_span=(0, 3),
            replacement_text="new",
        )
        changes = ChangeSet("changes", "local:test", (change,), "c" * 64)
        encryption = EncryptionInfo(
            True, "AES-256-GCM", 1, "local-master-v1", "local_secret_service"
        )
        store = LocalBackupStore(
            state / "backups", (target_root,), AesGcmBackupCipher(_TestKeys())
        )
        manifest = store.create(BackupRequest(
            "backup-1", "plan-1", "local:test", None, changes, encryption
        ), CancellationToken())
        factory = LocalUserRestoreTaskFactory(
            (HostCandidate("local:test", HostKind.LOCAL, "Local"),),
            config, root / "state", lambda: _TestKeys(),
        )
        preview = CreateRestorePreview().execute(manifest)
        approval = CreateRestoreApproval().execute(
            preview, "restore-approval-1", "tester", True
        )
        return factory, manifest, preview, approval, target, state

    def test_encrypted_restore_composes_preflight_execution_evidence_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            factory, manifest, preview, approval, target, state = self._fixture(Path(directory))
            target.write_text("new", encoding="utf-8")
            current_preview = CreateRestorePreview().execute(manifest)
            current_approval = CreateRestoreApproval().execute(
                current_preview, "restore-approval-2", "tester", True
            )
            authorization = factory.prepare(
                manifest.host_id, manifest.backup_id, current_preview, current_approval
            )(CancellationToken())

            evidence = factory(authorization)(CancellationToken())

            self.assertEqual(evidence.state, RestoreExecutionState.COMMITTED)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            execution_root = state / "restore-executions"
            self.assertEqual(execution_root.stat().st_mode & 0o777, 0o700)
            self.assertTrue(all(path.stat().st_mode & 0o777 == 0o600
                                for path in execution_root.iterdir()))
            self.assertEqual(
                RestoreExecutionStore(execution_root).list_strict()[0].state,
                RestoreExecutionState.COMMITTED,
            )
            self.assertTrue((state / "audit" / "HEAD").is_file())

    def test_changed_target_consumes_authorization_without_mutation_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            factory, manifest, preview, approval, target, state = self._fixture(Path(directory))
            authorization = factory.prepare(
                manifest.host_id, manifest.backup_id, preview, approval
            )(CancellationToken())
            target.write_text("external", encoding="utf-8")

            with self.assertRaises(AdapterError) as caught:
                factory(authorization)(CancellationToken())
            self.assertEqual(caught.exception.code, "stale_restore_target")
            self.assertEqual(target.read_text(encoding="utf-8"), "external")
            view = RestoreExecutionStore(state / "restore-executions").list_strict()[0]
            self.assertEqual(view.state, RestoreExecutionState.FAILED)
            with self.assertRaises(AdapterError) as replay:
                factory(authorization)(CancellationToken())
            self.assertEqual(replay.exception.code, "restore_authorization_consumed")

    def test_rejects_remote_host_before_state_or_secret_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            factory = LocalUserRestoreTaskFactory(
                (HostCandidate("ssh:test", HostKind.SSH, "SSH", "test"),),
                root / "config", root / "state", lambda: self.fail("secret accessed"),
            )
            with self.assertRaisesRegex(ValueError, "requires_local"):
                factory.prepare("ssh:test", "backup", object(), object())
            self.assertFalse((root / "state" / "llm-manager").exists())


@unittest.skipUnless(
    os.environ.get("LLM_MANAGER_SECRET_SERVICE_GATE") == "1",
    "explicit Secret Service desktop Gate is disabled",
)
class LocalUserRestoreSecretServiceGateTests(unittest.TestCase):
    def test_real_secret_service_encrypted_restore_and_key_cleanup(self) -> None:
        import secretstorage

        reference = f"phase5-local-restore-gate-{uuid.uuid4().hex}"
        attributes = {
            "application": "llm-manager",
            "purpose": "backup-encryption",
            "key-reference": reference,
        }
        connection = secretstorage.dbus_init()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = root / "config"
                target_root = config / "opencode"
                target_root.mkdir(parents=True)
                target = target_root / "opencode.json"
                target.write_text("old", encoding="utf-8")
                state = root / "state" / "llm-manager"
                state.mkdir(parents=True, mode=0o700)
                state.chmod(0o700)
                change = Change(
                    "change", str(target), ChangeOperation.REPLACE_FILE, "old", "new",
                    hashlib.sha256(b"old").hexdigest(), "masked", source_span=(0, 3),
                    replacement_text="new",
                )
                changes = ChangeSet("changes", "local:test", (change,), "c" * 64)
                encryption = EncryptionInfo(
                    True, "AES-256-GCM", 1, reference, "local_secret_service"
                )
                provider = SecretServiceKeyProvider(SecretStorageBackend())
                store = LocalBackupStore(
                    state / "backups", (target_root,), AesGcmBackupCipher(provider)
                )
                manifest = store.create(BackupRequest(
                    "backup-1", "plan-1", "local:test", None, changes, encryption
                ), CancellationToken())
                target.write_text("new", encoding="utf-8")
                preview = CreateRestorePreview().execute(manifest)
                approval = CreateRestoreApproval().execute(
                    preview, "restore-approval", "desktop-gate", True
                )
                factory = LocalUserRestoreTaskFactory(
                    (HostCandidate("local:test", HostKind.LOCAL, "Local"),),
                    config, root / "state",
                )
                authorization = factory.prepare(
                    manifest.host_id, manifest.backup_id, preview, approval
                )(CancellationToken())

                evidence = factory(authorization)(CancellationToken())

                self.assertEqual(evidence.state, RestoreExecutionState.COMMITTED)
                self.assertEqual(target.read_text(encoding="utf-8"), "old")
                self.assertEqual(len(list(secretstorage.search_items(connection, attributes))), 1)
                envelope = next((state / "backups").rglob("*.enc")).read_bytes()
                self.assertNotIn(b"old", envelope)
        finally:
            for item in secretstorage.search_items(connection, attributes):
                item.delete()
            self.assertEqual(list(secretstorage.search_items(connection, attributes)), [])


if __name__ == "__main__":
    unittest.main()
