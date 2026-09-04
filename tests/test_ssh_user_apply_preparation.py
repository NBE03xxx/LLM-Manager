from __future__ import annotations

import hashlib
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_manager.application.approval import CreateApprovalRecord
from llm_manager.application.errors import AdapterError
from llm_manager.application.optimization import stable_hash
from llm_manager.application.ports import CancellationToken, FileStat
from llm_manager.domain.enums import (
    ChangeOperation, HostKind, PlanStatus, ReportStatus, ValidationStatus,
)
from llm_manager.domain.models import (
    BackupItem, BackupManifest, Change, ChangeSet, DiagnosticReport,
    EncryptionInfo, HostCapabilities, HostInfo, OptimizationPlan,
    OptimizationProfile, ValidationResult,
)
from llm_manager.infrastructure.backup import BackupRestoreItem, LocalBackupStore
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher
from llm_manager.infrastructure.remote_backup import (
    DualCopyPrivilegedBackupStore, SandboxRemoteRecoveryStore,
)
from llm_manager.infrastructure.ssh_backup import SshSnapshotLocalBackupStore
from llm_manager.infrastructure.ssh_user_apply_preparation import (
    PrepareSshUserApply, PrepareSshUserRollback,
)


NOW = datetime(2026, 9, 4, 13, 0, tzinfo=UTC)
ABSOLUTE = "/home/remote/.config/opencode/opencode.jsonc"
RELATIVE = ".config/opencode/opencode.jsonc"
BEFORE = b'{"model":"old"}\n'
AFTER = b'{"model":"new"}\n'
BEFORE_HASH = hashlib.sha256(BEFORE).hexdigest()


class PrepareSshUserApplyTests(unittest.TestCase):
    def test_real_dual_store_verifies_captured_local_and_root_recovery_copies(self) -> None:
        report, plan, approval = _bound_inputs()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = SshSnapshotLocalBackupStore(
                LocalBackupStore(root / "local", (Path(ABSOLUTE).parent,)),
                _StableHost(report.host),
                frozenset({ABSOLUTE}),
            )
            remote = SandboxRemoteRecoveryStore(
                root / "remote", AesGcmBackupCipher(_Keys()),
                "remote-master-v1", sandbox=True,
            )
            backups = DualCopyPrivilegedBackupStore(local, remote)
            prepared = PrepareSshUserApply(
                backups, {ABSOLUTE: RELATIVE}, lambda: NOW
            ).execute(plan, report, approval, "ssh-user-real", CancellationToken())

            checks = backups.verify(prepared.manifest, CancellationToken())
            self.assertTrue(all(check.status is ValidationStatus.PASSED for check in checks))
            self.assertEqual(prepared.payload, AFTER)
            self.assertEqual(remote.load(prepared.manifest, CancellationToken()).key_scope, "remote_root")

    def test_prepares_bound_request_only_after_both_backup_checks_pass(self) -> None:
        report, plan, approval = _bound_inputs()
        backups = _Backups()
        prepared = PrepareSshUserApply(
            backups, {ABSOLUTE: RELATIVE}, lambda: NOW
        ).execute(plan, report, approval, "ssh-user-1", CancellationToken())

        self.assertEqual(backups.calls, ["create", "verify", "restore_items"])
        self.assertEqual(prepared.payload, AFTER)
        self.assertEqual(prepared.request.host_fingerprint, report.host.fingerprint)
        self.assertEqual(prepared.request.local_manifest_hash, prepared.manifest.manifest_hash)
        self.assertEqual(prepared.request.before_hash, BEFORE_HASH)
        self.assertEqual(prepared.request.after_hash, hashlib.sha256(AFTER).hexdigest())
        self.assertEqual(prepared.request.target, RELATIVE)

    def test_remote_copy_failure_stops_before_content_or_apply_preparation(self) -> None:
        report, plan, approval = _bound_inputs()
        backups = _Backups(remote_passed=False)
        with self.assertRaises(AdapterError) as caught:
            PrepareSshUserApply(backups, {ABSOLUTE: RELATIVE}, lambda: NOW).execute(
                plan, report, approval, "ssh-user-1", CancellationToken()
            )
        self.assertEqual(caught.exception.code, "backup_verification_failed")
        self.assertEqual(backups.calls, ["create", "verify"])

    def test_rejects_report_fingerprint_target_and_stale_backup_binding(self) -> None:
        report, plan, approval = _bound_inputs()
        no_fingerprint = replace(report, host=replace(report.host, fingerprint=None))
        with self.assertRaises(AdapterError):
            PrepareSshUserApply(_Backups(), {ABSOLUTE: RELATIVE}, lambda: NOW).execute(
                plan, no_fingerprint, approval, "ssh-user-1", CancellationToken()
            )

        with self.assertRaises(AdapterError) as target_error:
            PrepareSshUserApply(_Backups(), {}, lambda: NOW).execute(
                plan, report, approval, "ssh-user-1", CancellationToken()
            )
        self.assertEqual(target_error.exception.code, "unsupported_ssh_user_change")

        stale = _Backups(item_hash="f" * 64)
        with self.assertRaises(AdapterError) as stale_error:
            PrepareSshUserApply(stale, {ABSOLUTE: RELATIVE}, lambda: NOW).execute(
                plan, report, approval, "ssh-user-1", CancellationToken()
            )
        self.assertEqual(stale_error.exception.code, "backup_binding_mismatch")


class PrepareSshUserRollbackTests(unittest.TestCase):
    def test_builds_rollback_from_same_verified_manifest_and_apply_hash(self) -> None:
        report, plan, approval = _bound_inputs()
        backups = _Backups()
        prepared_apply = PrepareSshUserApply(
            backups, {ABSOLUTE: RELATIVE}, lambda: NOW
        ).execute(plan, report, approval, "ssh-user-1", CancellationToken())
        backups.calls.clear()

        rollback = PrepareSshUserRollback(backups, lambda: NOW).execute(
            plan, report, approval, prepared_apply, "ssh-user-1-rollback",
            CancellationToken(),
        )

        self.assertEqual(backups.calls, ["verify", "restore_items"])
        self.assertEqual(rollback.request.apply_request_hash, prepared_apply.request.request_hash)
        self.assertEqual(rollback.request.local_manifest_hash, prepared_apply.manifest.manifest_hash)
        self.assertEqual(rollback.request.expected_current_hash, prepared_apply.request.after_hash)
        self.assertEqual(rollback.request.restore_hash, BEFORE_HASH)
        self.assertEqual(rollback.request.restore_mode, 0o600)
        self.assertEqual(rollback.restore_content, BEFORE)

    def test_rejects_changed_manifest_payload_and_failed_remote_reverification(self) -> None:
        report, plan, approval = _bound_inputs()
        backups = _Backups()
        prepared = PrepareSshUserApply(
            backups, {ABSOLUTE: RELATIVE}, lambda: NOW
        ).execute(plan, report, approval, "ssh-user-1", CancellationToken())
        factory = PrepareSshUserRollback(backups, lambda: NOW)

        with self.assertRaises(AdapterError) as manifest_error:
            factory.execute(
                plan, report, approval,
                replace(prepared, manifest=replace(prepared.manifest, manifest_hash="f" * 64)),
                "rollback-1", CancellationToken(),
            )
        self.assertEqual(manifest_error.exception.code, "rollback_binding_mismatch")

        with self.assertRaises(AdapterError) as payload_error:
            factory.execute(
                plan, report, approval, replace(prepared, payload=b"changed"),
                "rollback-2", CancellationToken(),
            )
        self.assertEqual(payload_error.exception.code, "rollback_binding_mismatch")

        backups.remote_passed = False
        with self.assertRaises(AdapterError) as backup_error:
            factory.execute(
                plan, report, approval, prepared, "rollback-3", CancellationToken()
            )
        self.assertEqual(backup_error.exception.code, "backup_verification_failed")

    def test_started_apply_can_prepare_short_lived_rollback_after_approval_expiry(self) -> None:
        report, plan, approval = _bound_inputs()
        backups = _Backups()
        prepared = PrepareSshUserApply(
            backups, {ABSOLUTE: RELATIVE}, lambda: NOW
        ).execute(plan, report, approval, "ssh-user-1", CancellationToken())
        later = NOW + timedelta(minutes=6)
        rollback = PrepareSshUserRollback(backups, lambda: later).execute(
            plan, report, approval, prepared, "rollback-late", CancellationToken()
        )
        self.assertEqual(rollback.request.requested_at, later)
        self.assertEqual(rollback.request.expires_at, later + timedelta(minutes=5))


class _Backups:
    def __init__(self, *, remote_passed=True, item_hash=BEFORE_HASH):
        self.remote_passed = remote_passed
        self.item_hash = item_hash
        self.calls = []
        self.manifest = None

    def create(self, request, cancellation):
        self.calls.append("create")
        self.manifest = BackupManifest(
            request.backup_id, "1.0", request.plan_id, request.change_set.content_hash,
            request.host_id, request.host_fingerprint,
            (BackupItem(ABSOLUTE, True, "items/item.enc", BEFORE_HASH, 0o600, 1000, 1000),),
            "d" * 64, "/local/backup", request.encryption,
            created_at=NOW, retention_expires_at=NOW + timedelta(days=30), complete=True,
        )
        return self.manifest

    def verify(self, manifest, cancellation):
        self.calls.append("verify")
        return (
            ValidationResult("local", "backup", "local", ValidationStatus.PASSED),
            ValidationResult(
                "remote", "backup", "remote",
                ValidationStatus.PASSED if self.remote_passed else ValidationStatus.FAILED,
            ),
        )

    def restore_items(self, manifest, cancellation):
        self.calls.append("restore_items")
        content = BEFORE if self.item_hash == BEFORE_HASH else b"stale"
        return (BackupRestoreItem(ABSOLUTE, True, content, self.item_hash, 0o600, 1000, 1000),)


class _StableHost:
    def __init__(self, identity):
        self.identity = identity

    def identify(self, cancellation):
        return self.identity

    def capabilities(self):
        return HostCapabilities()

    def execute_readonly(self, request, cancellation):
        raise AssertionError("unexpected command")

    def stat(self, path, cancellation):
        return FileStat(path, True, BEFORE_HASH, 0o600, 1000, 1000, False)

    def read_file(self, path, max_bytes, cancellation):
        return BEFORE


class _Keys:
    def get_key(self, reference, scope):
        return b"r" * 32


def _bound_inputs():
    host = HostInfo(
        "ssh:remote", HostKind.SSH, "Remote", HostCapabilities(),
        ssh_alias="remote", fingerprint="SHA256:" + "a" * 43,
    )
    report = DiagnosticReport("report-1", "1.0", host, ReportStatus.COMPLETE)
    text = BEFORE.decode()
    start = text.index("old")
    change = Change(
        "change-1", ABSOLUTE, ChangeOperation.REPLACE_FILE, "old", "new",
        BEFORE_HASH, "diff", source_span=(start, start + 3), replacement_text="new",
    )
    change_set = ChangeSet("changes-1", host.host_id, (change,), "c" * 64, PlanStatus.DRAFT)
    plan = OptimizationPlan(
        "plan-1", report.report_id, stable_hash(report),
        OptimizationProfile("agent", 1, "Agent", ("stability",)), "1",
        (), (), change_set, PlanStatus.DRAFT, NOW, NOW + timedelta(minutes=10),
        EncryptionInfo(enabled=False),
    )
    approval = CreateApprovalRecord().execute(
        plan, "approval-1", "tester", True, True, NOW
    )
    return report, plan, approval


if __name__ == "__main__":
    unittest.main()
