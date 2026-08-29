import hashlib
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.adapters.fakes import FakeAuditAdapter
from llm_manager.domain.enums import ChangeOperation, PlanStatus, Severity, ValidationStatus
from llm_manager.domain.models import ApprovalRecord, Change, ChangeSet, LocalizedMessage, ValidationResult
from llm_manager.infrastructure.backup import LocalBackupStore, MAX_ITEM_BYTES
from llm_manager.infrastructure.safe_apply import AppliedFile, AtomicFileExecutor, FileValidator, SafeApplyCoordinator
from tests.fixtures import plan


def _change_set(path: Path, content: str, changes: tuple[Change, ...] | None = None) -> ChangeSet:
    digest = hashlib.sha256(content.encode()).hexdigest()
    default = Change("c1", str(path), ChangeOperation.REPLACE_FILE, content, "new", digest, "diff", source_span=(0, len(content)), replacement_text="new")
    return ChangeSet("cs", "host-1", changes or (default,), "set-hash")


class LocalBackupStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.targets = self.base / "targets"
        self.targets.mkdir()
        self.store = LocalBackupStore(self.base / "backups", (self.targets,))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_create_verify_restore_and_permissions(self) -> None:
        target = self.targets / "config.json"
        target.write_text("old", encoding="utf-8")
        target.chmod(0o640)
        manifest = self.store.create(BackupRequest("b1", "p1", "host-1", "fp", _change_set(target, "old")), CancellationToken())
        self.assertTrue(all(item.status is ValidationStatus.PASSED for item in self.store.verify(manifest, CancellationToken())))
        self.assertEqual(os.stat(manifest.storage_location).st_mode & 0o777, 0o700)
        self.assertEqual((Path(manifest.storage_location) / "manifest.json").stat().st_mode & 0o777, 0o600)
        target.write_text("changed", encoding="utf-8")
        restored = self.store.restore(manifest, CancellationToken())
        self.assertTrue(all(item.status is ValidationStatus.PASSED for item in restored))
        self.assertEqual(target.read_text(encoding="utf-8"), "old")
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)

    def test_manifest_or_content_tampering_is_detected(self) -> None:
        target = self.targets / "config"
        target.write_text("old", encoding="utf-8")
        manifest = self.store.create(BackupRequest("b1", "p1", "host-1", None, _change_set(target, "old")), CancellationToken())
        (Path(manifest.storage_location) / "manifest.json").write_text("{}", encoding="utf-8")
        self.assertTrue(any(item.status is ValidationStatus.FAILED for item in self.store.verify(manifest, CancellationToken())))

    def test_rejects_symlink_and_oversize(self) -> None:
        real = self.targets / "real"
        real.write_text("x", encoding="utf-8")
        link = self.targets / "link"
        link.symlink_to(real)
        with self.assertRaises(AdapterError):
            self.store.create(BackupRequest("b1", "p1", "host-1", None, _change_set(link, "x")), CancellationToken())
        huge = self.targets / "huge"
        with huge.open("wb") as handle:
            handle.truncate(MAX_ITEM_BYTES + 1)
        with self.assertRaises(AdapterError):
            self.store.create(BackupRequest("b2", "p1", "host-1", None, _change_set(huge, "")), CancellationToken())

    def test_retention_keeps_protected_and_last_backup(self) -> None:
        target = self.targets / "config"
        target.write_text("old", encoding="utf-8")
        first = self.store.create(BackupRequest("b1", "p1", "host-1", None, _change_set(target, "old")), CancellationToken())
        self.store.set_protected("host-1", "b1", True)
        second = self.store.create(BackupRequest("b2", "p1", "host-1", None, _change_set(target, "old")), CancellationToken())
        removed = self.store.prune("host-1", now=second.created_at + timedelta(days=31))
        self.assertEqual(removed, ("b2",))
        self.assertEqual(self.store.list_manifests("host-1")[0].backup_id, "b1")

    def test_manifests_and_protection_survive_store_restart(self) -> None:
        target = self.targets / "config"
        target.write_text("old", encoding="utf-8")
        self.store.create(BackupRequest("b1", "p1", "host-1", None, _change_set(target, "old")), CancellationToken())
        restarted = LocalBackupStore(self.base / "backups", (self.targets,))
        loaded = restarted.list_manifests("host-1")
        self.assertEqual([item.backup_id for item in loaded], ["b1"])
        protected = restarted.set_protected("host-1", "b1", True)
        self.assertTrue(protected.protected)
        restarted_again = LocalBackupStore(self.base / "backups", (self.targets,))
        self.assertTrue(restarted_again.list_manifests("host-1")[0].protected)
        self.assertTrue(all(item.status is ValidationStatus.PASSED for item in restarted_again.verify(protected, CancellationToken())))

    def test_restart_listing_ignores_tampered_or_wrong_host_manifest(self) -> None:
        target = self.targets / "config"
        target.write_text("old", encoding="utf-8")
        manifest = self.store.create(BackupRequest("b1", "p1", "host-1", None, _change_set(target, "old")), CancellationToken())
        manifest_path = Path(manifest.storage_location) / "manifest.json"
        payload = manifest_path.read_text(encoding="utf-8").replace('"host_id":"host-1"', '"host_id":"other"')
        manifest_path.write_text(payload, encoding="utf-8")
        restarted = LocalBackupStore(self.base / "backups", (self.targets,))
        self.assertEqual(restarted.list_manifests("host-1"), ())


class AtomicExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = AtomicFileExecutor((self.root,))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_groups_non_overlapping_spans_for_one_atomic_write(self) -> None:
        target = self.root / "config.json"
        original = '{"a":1,"b":2}'
        target.write_text(original, encoding="utf-8")
        digest = hashlib.sha256(original.encode()).hexdigest()
        changes = (
            Change("a", str(target), ChangeOperation.REPLACE_FILE, 1, 3, digest, "", source_span=(5, 6), replacement_text="3"),
            Change("b", str(target), ChangeOperation.REPLACE_FILE, 2, 4, digest, "", source_span=(11, 12), replacement_text="4"),
        )
        applied = self.executor.apply(_change_set(target, original, changes), CancellationToken())
        self.assertEqual(target.read_text(encoding="utf-8"), '{"a":3,"b":4}')
        self.assertEqual(len(applied), 1)

    def test_stale_hash_and_symlink_are_rejected(self) -> None:
        target = self.root / "config"
        target.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(AdapterError, "changed after planning"):
            self.executor.apply(_change_set(target, "old"), CancellationToken())
        real = self.root / "real"
        real.write_text("old", encoding="utf-8")
        link = self.root / "link"
        link.symlink_to(real)
        with self.assertRaises(AdapterError):
            self.executor.apply(_change_set(link, "old"), CancellationToken())


class FileValidatorTests(unittest.TestCase):
    def test_validates_jsonc_and_rejects_malformed_jsonc(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "opencode.jsonc"
            target.write_text('{// comment\n"model":"ollama/qwen"}', encoding="utf-8")
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            valid = FileValidator().validate((AppliedFile(str(target), digest, ("opencode.config.parse",)),), CancellationToken())
            self.assertTrue(all(item.status is ValidationStatus.PASSED for item in valid))
            target.write_text('{"model":}', encoding="utf-8")
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            invalid = FileValidator().validate((AppliedFile(str(target), digest, ("opencode.config.parse",)),), CancellationToken())
            self.assertTrue(any(item.status is ValidationStatus.FAILED for item in invalid))

    def test_validates_only_supported_systemd_drop_in_directives(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "90-llm-manager.conf"
            target.write_text('[Service]\nEnvironment="OLLAMA_HOST=127.0.0.1:11434"\n', encoding="utf-8")
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            valid = FileValidator().validate((AppliedFile(str(target), digest, ("systemd.daemon_reload",)),), CancellationToken())
            self.assertTrue(all(item.status is ValidationStatus.PASSED for item in valid))
            target.write_text("[Service]\nExecStart=/bin/false\n", encoding="utf-8")
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            invalid = FileValidator().validate((AppliedFile(str(target), digest, ("systemd.daemon_reload",)),), CancellationToken())
            self.assertTrue(any(item.status is ValidationStatus.FAILED for item in invalid))


class CoordinatorTests(unittest.TestCase):
    def test_success_and_validation_failure_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "config"
            target.write_text("old", encoding="utf-8")
            changes = _change_set(target, "old")
            current_plan = replace(plan(), change_set=changes)
            approval = ApprovalRecord("a", current_plan.plan_id, current_plan.report_hash, changes.content_hash, "tester")
            store = LocalBackupStore(root / "backups", (root,))
            coordinator = SafeApplyCoordinator(store, AtomicFileExecutor((root,)), FileValidator())
            outcome = coordinator.execute(current_plan, approval, "b1", CancellationToken())
            self.assertEqual(outcome.status, PlanStatus.COMMITTED)
            self.assertEqual(target.read_text(encoding="utf-8"), "new")

            target.write_text("old", encoding="utf-8")
            failing = _FailValidator()
            outcome = SafeApplyCoordinator(store, AtomicFileExecutor((root,)), failing).execute(current_plan, approval, "b2", CancellationToken())
            self.assertEqual(outcome.status, PlanStatus.ROLLED_BACK)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")

    def test_rollback_failure_requires_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "config"
            target.write_text("old", encoding="utf-8")
            changes = _change_set(target, "old")
            current_plan = replace(plan(), change_set=changes)
            approval = ApprovalRecord("a", current_plan.plan_id, current_plan.report_hash, changes.content_hash, "tester")
            store = _RestoreFailStore(LocalBackupStore(root / "backups", (root,)))
            outcome = SafeApplyCoordinator(store, AtomicFileExecutor((root,)), _FailValidator()).execute(current_plan, approval, "b1", CancellationToken())
            self.assertEqual(outcome.status, PlanStatus.RECOVERY_REQUIRED)

    def test_rollback_exception_requires_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "config"
            target.write_text("old", encoding="utf-8")
            changes = _change_set(target, "old")
            current_plan = replace(plan(), change_set=changes)
            approval = ApprovalRecord("a", current_plan.plan_id, current_plan.report_hash, changes.content_hash, "tester")
            store = _RestoreExceptionStore(LocalBackupStore(root / "backups", (root,)))
            outcome = SafeApplyCoordinator(store, AtomicFileExecutor((root,)), _FailValidator()).execute(current_plan, approval, "b1", CancellationToken())
            self.assertEqual(outcome.status, PlanStatus.RECOVERY_REQUIRED)
            self.assertTrue(any(item.check == "rollback.exception" for item in outcome.validations))

    def test_invalid_approval_is_rejected_before_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "config"
            target.write_text("old", encoding="utf-8")
            changes = _change_set(target, "old")
            current_plan = replace(plan(), change_set=changes)
            approval = ApprovalRecord("a", "wrong-plan", current_plan.report_hash, changes.content_hash, "tester")
            coordinator = SafeApplyCoordinator(LocalBackupStore(root / "backups", (root,)), AtomicFileExecutor((root,)), FileValidator())
            with self.assertRaises(AdapterError):
                coordinator.execute(current_plan, approval, "b1", CancellationToken())

    def test_atomic_write_failure_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "config"
            target.write_text("old", encoding="utf-8")
            changes = _change_set(target, "old")
            current_plan = replace(plan(), change_set=changes)
            approval = ApprovalRecord("a", current_plan.plan_id, current_plan.report_hash, changes.content_hash, "tester")
            coordinator = SafeApplyCoordinator(LocalBackupStore(root / "backups", (root,)), AtomicFileExecutor((root,)), FileValidator())
            with patch("llm_manager.infrastructure.safe_apply._atomic_write", side_effect=OSError("injected write failure")):
                outcome = coordinator.execute(current_plan, approval, "b1", CancellationToken())
            self.assertEqual(outcome.status, PlanStatus.ROLLED_BACK)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")

    def test_backup_failure_keeps_target_unchanged_and_is_audited(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "config"
            target.write_text("old", encoding="utf-8")
            changes = _change_set(target, "old")
            current_plan = replace(plan(), change_set=changes)
            approval = ApprovalRecord("a", current_plan.plan_id, current_plan.report_hash, changes.content_hash, "tester")
            audit = FakeAuditAdapter()
            coordinator = SafeApplyCoordinator(_BackupFailStore(), AtomicFileExecutor((root,)), FileValidator(), audit)
            outcome = coordinator.execute(current_plan, approval, "b1", CancellationToken())
            self.assertEqual(outcome.status, PlanStatus.APPROVED)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            self.assertEqual([event[0] for event in audit.events], ["apply.approved", "backup.failed"])


class _FailValidator(FileValidator):
    def validate(self, applied, cancellation):
        return (ValidationResult("fail", "file", "fail", ValidationStatus.FAILED, severity=Severity.HIGH, message=LocalizedMessage("fail")),)


class _RestoreFailStore:
    def __init__(self, delegate):
        self.delegate = delegate

    def create(self, request, cancellation):
        return self.delegate.create(request, cancellation)

    def verify(self, manifest, cancellation):
        return self.delegate.verify(manifest, cancellation)

    def restore(self, manifest, cancellation):
        return (ValidationResult("restore", "backup", "restore", ValidationStatus.FAILED),)

    def list_manifests(self, host_id):
        return self.delegate.list_manifests(host_id)

    def set_protected(self, host_id, backup_id, protected):
        return self.delegate.set_protected(host_id, backup_id, protected)


class _BackupFailStore:
    def create(self, request, cancellation):
        raise AdapterError("injected_backup_failure", "injected backup failure")

    def verify(self, manifest, cancellation):
        raise AssertionError("verify must not run")

    def restore(self, manifest, cancellation):
        raise AssertionError("restore must not run")

    def list_manifests(self, host_id):
        return ()

    def set_protected(self, host_id, backup_id, protected):
        raise AdapterError("backup_not_found", "no backups")


class _RestoreExceptionStore(_RestoreFailStore):
    def restore(self, manifest, cancellation):
        raise OSError("injected restore exception")


if __name__ == "__main__":
    unittest.main()
