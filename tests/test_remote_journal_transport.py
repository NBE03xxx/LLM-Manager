from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandResult, FileStat
from llm_manager.infrastructure.backup import _manifest_hash
from llm_manager.infrastructure.journal import (
    JournalStatus,
    JournalTarget,
    LocalOperationJournal,
    ReconciliationState,
    RemoteJournalReconciler,
)
from llm_manager.infrastructure.openssh_remote_journal import OpenSshRemoteJournalPort
from llm_manager.infrastructure.remote_journal import (
    RemoteJournalEvidence,
    RemoteRootJournalEvidenceStore,
    encode_remote_journal_evidence,
)
from tests.fixtures import host_info, manifest


class RemoteRootJournalEvidenceStoreTests(unittest.TestCase):
    def test_loads_only_private_canonical_bound_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "evidence"
            root.mkdir(mode=0o700)
            content = _evidence()
            path = root / "operation-1.json"
            path.write_bytes(content)
            os.chmod(path, 0o600)
            store = RemoteRootJournalEvidenceStore(root, sandbox=True)
            self.assertEqual(
                store.load_journal_evidence(
                    "operation-1", "a" * 64, CancellationToken()
                ),
                content,
            )

            with self.assertRaises(AdapterError):
                store.load_journal_evidence("operation-1", "b" * 64, CancellationToken())
            os.chmod(path, 0o644)
            with self.assertRaises(AdapterError):
                store.load_journal_evidence("operation-1", "a" * 64, CancellationToken())
            path.unlink()
            outside = Path(directory) / "outside.json"
            outside.write_bytes(content)
            path.symlink_to(outside)
            with self.assertRaises(AdapterError):
                store.load_journal_evidence("operation-1", "a" * 64, CancellationToken())

    def test_rejects_alternate_production_root_and_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "evidence"
            root.mkdir(mode=0o700)
            with self.assertRaises(AdapterError):
                RemoteRootJournalEvidenceStore(root)
            store = RemoteRootJournalEvidenceStore(root, sandbox=True)
            with self.assertRaises(OperationCancelled):
                store.load_journal_evidence(
                    "operation-1", "a" * 64, CancellationToken(cancelled=True)
                )


class OpenSshRemoteJournalPortTests(unittest.TestCase):
    def test_fetches_with_fixed_passwordless_root_helper_command(self) -> None:
        content = _evidence()
        runner = _Runner(CommandResult(("ssh",), 0, content.decode(), "", False, 1))
        gate = _Gate()
        port = OpenSshRemoteJournalPort(
            "development", runner, gate, control_socket="/tmp/llm-manager-cm"
        )
        self.assertEqual(
            port.load_journal_evidence("operation-1", "a" * 64, CancellationToken()),
            content,
        )
        argv = runner.requests[0].argv
        self.assertEqual(argv[:6], ("ssh", "-S", "/tmp/llm-manager-cm", "-o", "BatchMode=yes", "--"))
        self.assertEqual(
            argv[-1],
            "sudo -n -- /usr/bin/llm-manager-remote-helper read-journal-evidence operation-1 "
            + "a" * 64,
        )
        self.assertEqual(gate.calls, 1)

    def test_gate_timeout_failure_cancel_and_identity_fail_closed(self) -> None:
        for result, code in (
            (CommandResult(("ssh",), None, "", "", True, 1), "remote_journal_timeout"),
            (CommandResult(("ssh",), 1, "", "failed", False, 1), "remote_journal_failed"),
        ):
            with self.subTest(code=code):
                port = OpenSshRemoteJournalPort("host", _Runner(result), _Gate())
                with self.assertRaises(AdapterError) as caught:
                    port.load_journal_evidence("operation-1", "a" * 64, CancellationToken())
                self.assertEqual(caught.exception.code, code)
        runner = _Runner(CommandResult(("ssh",), 0, "", "", False, 1))
        port = OpenSshRemoteJournalPort("host", runner, _Gate())
        with self.assertRaises(OperationCancelled):
            port.load_journal_evidence(
                "operation-1", "a" * 64, CancellationToken(cancelled=True)
            )
        with self.assertRaises(AdapterError):
            port.load_journal_evidence("../bad", "x" * 64, CancellationToken())
        self.assertEqual(runner.requests, [])
        blocked = _Gate(AdapterError("privileged_helper_unavailable", "incompatible"))
        port = OpenSshRemoteJournalPort("host", runner, blocked)
        with self.assertRaises(AdapterError):
            port.load_journal_evidence("operation-1", "a" * 64, CancellationToken())
        self.assertEqual(runner.requests, [])
        oversized = OpenSshRemoteJournalPort(
            "host",
            _Runner(CommandResult(("ssh",), 0, "x" * (1024 * 1024 + 1), "", False, 1)),
            _Gate(),
        )
        with self.assertRaises(AdapterError) as caught:
            oversized.load_journal_evidence(
                "operation-1", "a" * 64, CancellationToken()
            )
        self.assertEqual(caught.exception.code, "remote_journal_too_large")

    def test_transport_feeds_verified_evidence_to_readonly_reconciler(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target_root = Path(directory) / "targets"
            target_root.mkdir()
            local = LocalOperationJournal(Path(directory) / "journal", (target_root,))
            current_manifest = replace(
                manifest(), backup_id="operation-1", plan_id="plan-1",
                change_set_hash="c" * 64, host_id="ssh:host",
                host_fingerprint="SHA256:" + "f" * 43,
                manifest_hash="", complete=True,
            )
            current_manifest = replace(
                current_manifest, manifest_hash=_manifest_hash(current_manifest)
            )
            target = target_root / "config"
            local.create(
                "operation-1", "plan-1", "ssh:host", "c" * 64,
                (JournalTarget(str(target), "b" * 64, "e" * 64),),
                approval_id="approval-1", backup_id="operation-1",
                manifest_hash=current_manifest.manifest_hash, request_hash="a" * 64,
            )
            journal = local.load("operation-1")
            evidence = encode_remote_journal_evidence(
                RemoteJournalEvidence(
                    "1.0", journal.operation_id, journal.plan_id, journal.host_id,
                    current_manifest.host_fingerprint, journal.change_set_hash,
                    journal.backup_id, journal.manifest_hash, journal.request_hash,
                    journal.rollback_request_hash, journal.status, journal.targets,
                    "f" * 64,
                ).with_hash()
            )
            port = OpenSshRemoteJournalPort(
                "host",
                _Runner(CommandResult(("ssh",), 0, evidence.decode(), "", False, 1)),
                _Gate(),
            )
            result = RemoteJournalReconciler(local, port).reconcile(
                "operation-1", current_manifest,
                _Host(current_manifest.host_fingerprint, "b" * 64),
                CancellationToken(),
            )
            self.assertEqual(result[0].state, ReconciliationState.UNAPPLIED)

            changed_status = encode_remote_journal_evidence(
                replace(
                    RemoteJournalEvidence(
                        "1.0", journal.operation_id, journal.plan_id, journal.host_id,
                        current_manifest.host_fingerprint, journal.change_set_hash,
                        journal.backup_id, journal.manifest_hash, journal.request_hash,
                        journal.rollback_request_hash, JournalStatus.COMMITTED,
                        journal.targets, "f" * 64,
                    ),
                    evidence_hash="",
                ).with_hash()
            )
            changed_port = OpenSshRemoteJournalPort(
                "host",
                _Runner(CommandResult(("ssh",), 0, changed_status.decode(), "", False, 1)),
                _Gate(),
            )
            with self.assertRaises(AdapterError) as caught:
                RemoteJournalReconciler(local, changed_port).reconcile(
                    "operation-1", current_manifest,
                    _Host(current_manifest.host_fingerprint, "b" * 64),
                    CancellationToken(),
                )
            self.assertEqual(caught.exception.code, "remote_journal_unverified")


def _evidence() -> bytes:
    return encode_remote_journal_evidence(
        RemoteJournalEvidence(
            "1.0",
            "operation-1",
            "plan-1",
            "ssh:host",
            "SHA256:" + "f" * 43,
            "c" * 64,
            "backup-1",
            "d" * 64,
            "a" * 64,
            None,
            JournalStatus.APPLYING,
            (JournalTarget("/etc/example", "b" * 64, "e" * 64),),
            "f" * 64,
        ).with_hash()
    )


class _Runner:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def run(self, request, cancellation):
        self.requests.append(request)
        return self.result


class _Gate:
    def __init__(self, error=None):
        self.error = error
        self.calls = 0

    def assert_ready(self, cancellation):
        self.calls += 1
        if self.error:
            raise self.error


class _Host:
    def __init__(self, fingerprint, digest):
        self.fingerprint = fingerprint
        self.digest = digest

    def identify(self, cancellation):
        return replace(host_info(), host_id="ssh:host", fingerprint=self.fingerprint)

    def stat(self, path, cancellation):
        return FileStat(path, True, sha256=self.digest)


if __name__ == "__main__":
    unittest.main()
