from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.domain.enums import ChangeOperation
from llm_manager.domain.models import Change, ChangeSet, EncryptionInfo
from llm_manager.infrastructure.backup import LocalBackupStore
from llm_manager.infrastructure.backup_deletion import (
    BackupDeletionResult, BackupDeletionView, CopyDeleteOutcome,
)
from llm_manager.infrastructure.backup_inventory import (
    BackupInventoryService, BackupListAction, LocalRetentionResult,
    LocalRetentionResultStore, LocalRetentionRunner, RetentionRunEvidence,
)
from llm_manager.infrastructure.backup_reconciliation import CopyPresence, DualCopyState
from llm_manager.infrastructure.remote_backup import RemoteRetentionRecord
from llm_manager.infrastructure.remote_retention import (
    RemoteRetentionResult, RemoteRetentionState,
)


NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)
FINGERPRINT = "SHA256:" + "a" * 43


class BackupInventoryServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        target = root / "target"
        target.write_bytes(b"before")
        change = Change("change", str(target), ChangeOperation.REPLACE_FILE,
                        "before", "after", None, "diff")
        local = LocalBackupStore(root / "local", (root,))
        self.manifest = local.create(BackupRequest(
            "backup-1", "plan-1", "ssh:host", FINGERPRINT,
            ChangeSet("changes", "ssh:host", (change,), "c" * 64),
            EncryptionInfo(enabled=False),
        ), CancellationToken())
        self.record = RemoteRetentionRecord(
            "1.0", "backup-1", "ssh:host", "b" * 64, NOW,
            NOW + timedelta(days=30), False, "c" * 64,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_combines_local_remote_and_allows_new_dual_delete(self):
        item = BackupInventoryService(
            _Local((self.manifest,)), _Remote((self.record,))
        ).list_for_host("ssh:host", FINGERPRINT, CancellationToken())[0]
        self.assertEqual(item.state, DualCopyState.BOTH_AVAILABLE)
        self.assertFalse(item.requires_attention)
        self.assertEqual(item.allowed_actions, (BackupListAction.START_DUAL_DELETE,))

    def test_retry_policy_is_limited_by_bound_deletion_evidence(self):
        cases = (
            (
                _view(self.manifest, CopyDeleteOutcome.FAILED,
                      CopyDeleteOutcome.NOT_ATTEMPTED, DualCopyState.BOTH_AVAILABLE),
                (self.manifest,), (self.record,),
                BackupListAction.RETRY_REMOTE_DELETE,
            ),
            (
                _view(self.manifest, CopyDeleteOutcome.UNKNOWN,
                      CopyDeleteOutcome.NOT_ATTEMPTED, DualCopyState.LOCAL_ONLY),
                (self.manifest,), (), BackupListAction.RECOVER_REMOTE_RESULT,
            ),
            (
                _view(self.manifest, CopyDeleteOutcome.DELETED,
                      CopyDeleteOutcome.FAILED, DualCopyState.LOCAL_ONLY),
                (self.manifest,), (), BackupListAction.RETRY_LOCAL_DELETE,
            ),
            (
                _view(self.manifest, CopyDeleteOutcome.DELETED,
                      CopyDeleteOutcome.DELETED, DualCopyState.BOTH_DELETED,
                      cleanup_pending=True),
                (), (), BackupListAction.RETRY_STAGING_CLEANUP,
            ),
        )
        for view, local, remote, action in cases:
            with self.subTest(action=action):
                item = BackupInventoryService(
                    _Local(local), _Remote(remote)
                ).list_for_host(
                    "ssh:host", FINGERPRINT, CancellationToken(),
                    deletion_views=(view,),
                )[0]
                self.assertIn(action, item.allowed_actions)
                mutation_actions = {
                    BackupListAction.START_DUAL_DELETE,
                    BackupListAction.RETRY_REMOTE_DELETE,
                    BackupListAction.RETRY_LOCAL_DELETE,
                }
                self.assertEqual(
                    set(item.allowed_actions) & mutation_actions,
                    {action} if action in mutation_actions else set(),
                )

    def test_protected_unknown_and_remote_only_do_not_offer_mutation(self):
        protected = RemoteRetentionRecord(
            "1.0", "backup-1", "ssh:host", "b" * 64, NOW,
            NOW + timedelta(days=30), True, "c" * 64,
        )
        for local, remote in (
            (_Local(error=True), _Remote((self.record,))),
            (_Local(()), _Remote((protected,))),
        ):
            item = BackupInventoryService(local, remote).list_for_host(
                "ssh:host", FINGERPRINT, CancellationToken()
            )[0]
            self.assertNotIn(BackupListAction.START_DUAL_DELETE, item.allowed_actions)
            self.assertNotIn(BackupListAction.RETRY_LOCAL_DELETE, item.allowed_actions)
            self.assertNotIn(BackupListAction.RETRY_REMOTE_DELETE, item.allowed_actions)

    def test_retention_evidence_is_displayed_and_partial_requires_reconciliation(self):
        result = RemoteRetentionResult(
            "1.0", "retention-1", "a" * 64, "ssh:host", FINGERPRINT,
            NOW, RemoteRetentionState.PARTIAL, ("backup-1",), (),
            "delete_failed",
        ).with_hash()
        item = BackupInventoryService(_Local(()), _Remote(())).list_for_host(
            "ssh:host", FINGERPRINT, CancellationToken(),
            retention=RetentionRunEvidence(LocalRetentionResult(
                "1.0", "local-retention-1", "ssh:host", NOW,
                RemoteRetentionState.COMPLETED, ("backup-1",), (), None,
            ).with_hash(), result),
        )[0]
        self.assertTrue(item.local_retention_removed)
        self.assertTrue(item.remote_retention_removed)
        self.assertEqual(item.local_retention_state, RemoteRetentionState.COMPLETED)
        self.assertEqual(item.remote_retention_state, RemoteRetentionState.PARTIAL)
        self.assertIn(BackupListAction.RECONCILE_COPIES, item.allowed_actions)

    def test_rejects_cross_host_operation_evidence(self):
        result = RemoteRetentionResult(
            "1.0", "retention-1", "a" * 64, "ssh:other", FINGERPRINT,
            NOW, RemoteRetentionState.COMPLETED, (), (), None,
        ).with_hash()
        with self.assertRaises(AdapterError):
            BackupInventoryService(_Local(()), _Remote(())).list_for_host(
                "ssh:host", FINGERPRINT, CancellationToken(),
                retention=RetentionRunEvidence(remote_result=result),
            )

    def test_local_retention_runner_reconciles_backend_result(self):
        backend = _LocalRetentionBackend((self.manifest,))
        store = LocalRetentionResultStore(Path(self.temp.name) / "retention-results")
        result = LocalRetentionRunner(backend, store).prune(
            "local-retention-1", "ssh:host", NOW
        )
        self.assertEqual(result.state, RemoteRetentionState.COMPLETED)
        self.assertEqual(result.removed_backup_ids, ("backup-1",))
        self.assertEqual(result.remaining_backup_ids, ())
        self.assertEqual(store.load("local-retention-1"), result)
        self.assertEqual((Path(self.temp.name) / "retention-results").stat().st_mode & 0o777, 0o700)
        with self.assertRaises(AdapterError):
            store.save(result)

    def test_local_retention_store_rejects_tamper(self):
        store = LocalRetentionResultStore(Path(self.temp.name) / "retention-results")
        result = LocalRetentionResult(
            "1.0", "local-retention-2", "ssh:host", NOW,
            RemoteRetentionState.COMPLETED, (), ("backup-1",), None,
        ).with_hash()
        store.save(result)
        path = Path(self.temp.name) / "retention-results/local-retention-2.json"
        path.write_bytes(path.read_bytes()[:-1] + b" ")
        with self.assertRaises(AdapterError):
            store.load("local-retention-2")


class _Local:
    def __init__(self, values=(), error=False):
        self.values, self.error = tuple(values), error

    def list_manifests(self, host_id):
        if self.error:
            raise AdapterError("local_inventory_failed", "injected")
        return self.values


class _Remote:
    def __init__(self, values=(), error=False):
        self.values, self.error = tuple(values), error

    def list_retention(self, host_id, *, expected_fingerprint=None):
        if self.error:
            raise AdapterError("remote_inventory_failed", "injected")
        return self.values


class _LocalRetentionBackend:
    def __init__(self, values):
        self.values = tuple(values)

    def list_manifests(self, host_id):
        return self.values

    def prune(self, host_id, now=None, keep_generations=10):
        removed = tuple(item.backup_id for item in self.values)
        self.values = ()
        return removed


def _view(manifest, remote_outcome, local_outcome, state, cleanup_pending=False):
    presence = {
        DualCopyState.BOTH_AVAILABLE: (CopyPresence.PRESENT, CopyPresence.PRESENT),
        DualCopyState.LOCAL_ONLY: (CopyPresence.PRESENT, CopyPresence.ABSENT),
        DualCopyState.BOTH_DELETED: (CopyPresence.ABSENT, CopyPresence.ABSENT),
    }[state]
    remote_error = (
        "remote_failed" if remote_outcome is CopyDeleteOutcome.FAILED else
        "delete_observation_failed" if remote_outcome is CopyDeleteOutcome.UNKNOWN else None
    )
    local_error = (
        "local_failed" if local_outcome is CopyDeleteOutcome.FAILED else None
    )
    attention = (
        state not in {DualCopyState.BOTH_AVAILABLE, DualCopyState.BOTH_DELETED}
        or remote_outcome in {CopyDeleteOutcome.FAILED, CopyDeleteOutcome.UNKNOWN}
        or local_outcome in {
            CopyDeleteOutcome.FAILED, CopyDeleteOutcome.NOT_ATTEMPTED,
            CopyDeleteOutcome.UNKNOWN,
        }
    )
    result = BackupDeletionResult(
        "1.0", "delete-1", "a" * 64, manifest.backup_id, manifest.host_id,
        manifest.host_fingerprint, manifest.manifest_hash, remote_outcome,
        local_outcome, remote_error, local_error, presence[0], presence[1], state,
        attention, NOW,
    ).with_hash()
    return BackupDeletionView(result, cleanup_pending)


if __name__ == "__main__":
    unittest.main()
