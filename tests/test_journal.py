import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, FileStat
from llm_manager.infrastructure.backup import _manifest_hash
from llm_manager.infrastructure.journal import JournalStatus, JournalTarget, LocalOperationJournal, ReconciliationState, RemoteJournalReconciler
from llm_manager.infrastructure.remote_journal import RemoteJournalEvidence, encode_remote_journal_evidence
from tests.fixtures import host_info, manifest


class LocalOperationJournalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.targets = self.base / "targets"
        self.targets.mkdir()
        self.target = self.targets / "config"
        self.target.write_text("before", encoding="utf-8")
        self.before = hashlib.sha256(b"before").hexdigest()
        self.after = hashlib.sha256(b"after").hexdigest()
        self.store = LocalOperationJournal(self.base / "journal", (self.targets,))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_persists_updates_and_reloads_with_private_permissions(self) -> None:
        created = self.store.create("op-1", "plan-1", "host-1", "change-hash", (JournalTarget(str(self.target), self.before, self.after),))
        self.assertEqual(created.status, JournalStatus.APPLYING)
        updated = self.store.update("op-1", JournalStatus.VALIDATING)
        restarted = LocalOperationJournal(self.base / "journal", (self.targets,))
        self.assertEqual(restarted.load("op-1"), updated)
        self.assertEqual((self.base / "journal").stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.base / "journal" / "op-1.json").stat().st_mode & 0o777, 0o600)
        with self.assertRaises(AdapterError):
            self.store.update("op-1", JournalStatus.APPLYING)

    def test_reconciles_before_after_missing_and_unknown(self) -> None:
        missing = self.targets / "created"
        self.store.create("op-1", "plan-1", "host-1", "change-hash", (
            JournalTarget(str(self.target), self.before, self.after),
            JournalTarget(str(missing), None, self.after),
        ))
        initial = self.store.reconcile("op-1")
        self.assertEqual([item.state for item in initial], [ReconciliationState.UNAPPLIED, ReconciliationState.UNAPPLIED])
        self.target.write_text("after", encoding="utf-8")
        missing.write_text("after", encoding="utf-8")
        applied = self.store.reconcile("op-1")
        self.assertEqual([item.state for item in applied], [ReconciliationState.APPLIED, ReconciliationState.APPLIED])
        self.target.write_text("external", encoding="utf-8")
        self.assertEqual(self.store.reconcile("op-1")[0].state, ReconciliationState.UNKNOWN)

    def test_rejects_tamper_replay_and_outside_target(self) -> None:
        self.store.create("op-1", "plan-1", "host-1", "change-hash", (JournalTarget(str(self.target), self.before, self.after),))
        path = self.base / "journal" / "op-1.json"
        path.write_text(path.read_text(encoding="utf-8").replace('"status":"applying"', '"status":"committed"'), encoding="utf-8")
        with self.assertRaises(AdapterError):
            self.store.load("op-1")
        with self.assertRaises(AdapterError):
            self.store.create("op-1", "plan-1", "host-1", "change-hash", (JournalTarget(str(self.target), self.before, self.after),))
        outside = self.base / "outside"
        with self.assertRaises(AdapterError):
            self.store.create("op-2", "plan-1", "host-1", "change-hash", (JournalTarget(str(outside), None, self.after),))

    def test_remote_reconciliation_binds_host_manifest_and_hashes(self) -> None:
        current_manifest = replace(
            manifest(),
            backup_id="op-remote",
            plan_id="plan-1",
            change_set_hash="change-hash",
            host_id="ssh:gpu-box",
            host_fingerprint="SHA256:" + "a" * 43,
            manifest_hash="",
            complete=True,
        )
        current_manifest = replace(
            current_manifest,
            manifest_hash=_manifest_hash(current_manifest),
        )
        remote_store = LocalOperationJournal(
            self.base / "remote-journal", (Path("/etc/systemd/system"),)
        )
        remote_store.create(
            "op-remote", "plan-1", "ssh:gpu-box", "change-hash",
            (JournalTarget("/etc/systemd/system/ollama.service.d/90-llm-manager.conf", self.before, self.after),),
            approval_id="approval", backup_id="op-remote",
            manifest_hash=current_manifest.manifest_hash, request_hash="e" * 64,
        )
        remote = _RemoteHost(current_manifest.host_fingerprint, self.before)
        reconciler = RemoteJournalReconciler(
            remote_store, _EvidencePort(remote_store, current_manifest.host_fingerprint)
        )
        result = reconciler.reconcile("op-remote", current_manifest, remote, CancellationToken())
        self.assertEqual(result[0].state, ReconciliationState.UNAPPLIED)
        remote.digest = self.after
        self.assertEqual(
            reconciler.reconcile("op-remote", current_manifest, remote, CancellationToken())[0].state,
            ReconciliationState.APPLIED,
        )
        remote.digest = "f" * 64
        self.assertEqual(
            reconciler.reconcile("op-remote", current_manifest, remote, CancellationToken())[0].state,
            ReconciliationState.UNKNOWN,
        )

    def test_remote_reconciliation_rejects_identity_binding_and_disconnect(self) -> None:
        current_manifest = replace(
            manifest(), backup_id="op-remote", plan_id="plan-1",
            change_set_hash="change-hash", host_id="ssh:gpu-box",
            host_fingerprint="SHA256:" + "a" * 43,
            manifest_hash="", complete=True,
        )
        current_manifest = replace(
            current_manifest,
            manifest_hash=_manifest_hash(current_manifest),
        )
        remote_store = LocalOperationJournal(
            self.base / "remote-journal", (Path("/etc/systemd/system"),)
        )
        remote_store.create(
            "op-remote", "plan-1", "ssh:gpu-box", "change-hash",
            (JournalTarget("/etc/systemd/system/ollama.service.d/90-llm-manager.conf", self.before, self.after),),
            approval_id="approval", backup_id="op-remote",
            manifest_hash=current_manifest.manifest_hash, request_hash="e" * 64,
        )
        reconciler = RemoteJournalReconciler(
            remote_store, _EvidencePort(remote_store, current_manifest.host_fingerprint)
        )
        for changed in (
            replace(current_manifest, manifest_hash="c" * 64),
            replace(current_manifest, host_fingerprint=None),
        ):
            with self.subTest(changed=changed), self.assertRaises(AdapterError):
                reconciler.reconcile(
                    "op-remote", changed,
                    _RemoteHost(current_manifest.host_fingerprint, self.before),
                    CancellationToken(),
                )
        wrong_host = _RemoteHost("SHA256:" + "b" * 43, self.before)
        with self.assertRaises(AdapterError) as caught:
            reconciler.reconcile("op-remote", current_manifest, wrong_host, CancellationToken())
        self.assertEqual(caught.exception.code, "recovery_host_mismatch")
        disconnected = _RemoteHost(current_manifest.host_fingerprint, self.before, fail=True)
        with self.assertRaises(AdapterError) as caught:
            reconciler.reconcile("op-remote", current_manifest, disconnected, CancellationToken())
        self.assertEqual(caught.exception.code, "remote_reconciliation_failed")
        with self.assertRaises(OperationCancelled):
            reconciler.reconcile(
                "op-remote", current_manifest,
                _RemoteHost(current_manifest.host_fingerprint, self.before),
                CancellationToken(cancelled=True),
            )

    def test_remote_root_journal_tamper_or_disconnect_prevents_stat_reconciliation(self) -> None:
        current_manifest = replace(
            manifest(), backup_id="op-remote", plan_id="plan-1",
            change_set_hash="change-hash", host_id="ssh:gpu-box",
            host_fingerprint="SHA256:" + "a" * 43,
            manifest_hash="", complete=True,
        )
        current_manifest = replace(current_manifest, manifest_hash=_manifest_hash(current_manifest))
        store = LocalOperationJournal(self.base / "remote-evidence", (Path("/etc/systemd/system"),))
        store.create(
            "op-remote", "plan-1", "ssh:gpu-box", "change-hash",
            (JournalTarget("/etc/systemd/system/ollama.service.d/90-llm-manager.conf", self.before, self.after),),
            approval_id="approval", backup_id="op-remote",
            manifest_hash=current_manifest.manifest_hash, request_hash="e" * 64,
        )
        for mode in ("tamper", "disconnect", "wrong-binding"):
            with self.subTest(mode=mode):
                host = _RemoteHost(current_manifest.host_fingerprint, self.before)
                reconciler = RemoteJournalReconciler(
                    store, _EvidencePort(store, current_manifest.host_fingerprint, mode=mode)
                )
                with self.assertRaises(AdapterError) as caught:
                    reconciler.reconcile("op-remote", current_manifest, host, CancellationToken())
                self.assertEqual(caught.exception.code, "remote_journal_unverified")
                self.assertEqual(host.identify_calls, 0)
                self.assertEqual(host.stat_calls, 0)


class _RemoteHost:
    def __init__(self, fingerprint, digest, fail=False):
        self.fingerprint = fingerprint
        self.digest = digest
        self.fail = fail
        self.identify_calls = 0
        self.stat_calls = 0

    def identify(self, cancellation):
        self.identify_calls += 1
        return replace(
            host_info(), host_id="ssh:gpu-box", fingerprint=self.fingerprint,
        )

    def stat(self, path, cancellation):
        self.stat_calls += 1
        if self.fail:
            raise OSError("injected disconnect")
        return FileStat(path, True, sha256=self.digest)


class _EvidencePort:
    def __init__(self, store, fingerprint, mode=None):
        self.store = store
        self.fingerprint = fingerprint
        self.mode = mode

    def load_journal_evidence(self, operation_id, request_hash, cancellation):
        if self.mode == "disconnect":
            raise OSError("injected journal retrieval disconnect")
        journal = self.store.load(operation_id)
        evidence = RemoteJournalEvidence(
            "1.0", journal.operation_id, journal.plan_id, journal.host_id,
            self.fingerprint, journal.change_set_hash, journal.backup_id,
            journal.manifest_hash, journal.request_hash, journal.rollback_request_hash,
            journal.status, journal.targets, "f" * 64,
        ).with_hash()
        if self.mode == "wrong-binding":
            evidence = replace(evidence, manifest_hash="a" * 64, evidence_hash="").with_hash()
        content = encode_remote_journal_evidence(evidence)
        return content + b"\n" if self.mode == "tamper" else content


if __name__ == "__main__":
    unittest.main()
