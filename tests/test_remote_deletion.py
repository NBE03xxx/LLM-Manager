from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import BackupRequest, CancellationToken, CommandResult
from llm_manager.domain.enums import ChangeOperation
from llm_manager.domain.models import Change, ChangeSet, EncryptionInfo
from llm_manager.infrastructure.backup import LocalBackupStore
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher
from llm_manager.infrastructure.openssh_remote_deletion import (
    OpenSshRemoteDeletionInvoker, OpenSshRemoteDeletionPort,
)
from llm_manager.infrastructure.remote_backup import SandboxRemoteRecoveryStore
from llm_manager.infrastructure.remote_deletion import (
    RemoteDeletionHelperExecutor, RemoteDeletionOutcome,
    RemoteDeletionResult, decode_remote_deletion_request,
    decode_remote_deletion_result, encode_remote_deletion_request,
    encode_remote_deletion_result, new_remote_deletion_request,
)


NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)


class RemoteDeletionProtocolTests(unittest.TestCase):
    def test_canonical_request_and_result_are_hash_and_time_bound(self):
        factory = _Factory()
        request = new_remote_deletion_request(
            "delete-remote-1", factory.manifest, factory.receipt, now=NOW
        )
        content = encode_remote_deletion_request(request)
        self.assertEqual(decode_remote_deletion_request(
            content, expected_hash=request.request_hash, now=NOW), request)
        with self.assertRaises(AdapterError):
            decode_remote_deletion_request(
                content + b"\n", expected_hash=request.request_hash, now=NOW)
        with self.assertRaises(AdapterError):
            decode_remote_deletion_request(
                content, expected_hash=request.request_hash,
                now=NOW + timedelta(minutes=6),
            )
        result = RemoteDeletionResult(
            "1.0", request.request_id, request.request_hash, request.backup_id,
            request.host_id, request.host_fingerprint, request.manifest_hash,
            request.remote_receipt_hash, request.key_reference,
            RemoteDeletionOutcome.DELETED, None, NOW,
        ).with_hash()
        self.assertEqual(decode_remote_deletion_result(
            encode_remote_deletion_result(result)), result)
        factory.close()


class RemoteDeletionHelperExecutorTests(unittest.TestCase):
    def test_verifies_receipt_decrypts_and_deletes_through_fixed_staging(self):
        factory = _Factory()
        request = new_remote_deletion_request(
            "delete-remote-2", factory.manifest, factory.receipt, now=NOW
        )
        operation = _stage(factory.staging, request)
        result = decode_remote_deletion_result(RemoteDeletionHelperExecutor(
            factory.staging, factory.remote, os.getuid(), clock=lambda: NOW
        ).execute(request.request_id, request.request_hash, CancellationToken()))
        self.assertEqual(result.outcome, RemoteDeletionOutcome.DELETED)
        self.assertEqual((operation / "result.json").stat().st_mode & 0o777, 0o600)
        with self.assertRaises(AdapterError) as caught:
            factory.remote.load(factory.manifest, CancellationToken())
        self.assertEqual(caught.exception.code, "remote_backup_not_found")
        factory.close()

    def test_tampered_binding_and_protected_copy_are_not_deleted(self):
        for case in ("receipt_hash", "protected"):
            factory = _Factory(protected=case == "protected")
            request = new_remote_deletion_request(
                f"delete-remote-{case}", factory.manifest, factory.receipt, now=NOW
            )
            if case == "receipt_hash":
                request = replace(
                    request, remote_receipt_hash="f" * 64
                ).with_hash()
            _stage(factory.staging, request)
            result = decode_remote_deletion_result(RemoteDeletionHelperExecutor(
                factory.staging, factory.remote, os.getuid(), clock=lambda: NOW
            ).execute(request.request_id, request.request_hash, CancellationToken()))
            self.assertEqual(result.outcome, RemoteDeletionOutcome.FAILED)
            factory.remote.load(factory.manifest, CancellationToken())
            factory.close()

    def test_unsafe_receipt_is_failed_not_mistaken_for_absent(self):
        factory = _Factory()
        request = new_remote_deletion_request(
            "delete-remote-unsafe", factory.manifest, factory.receipt, now=NOW
        )
        _stage(factory.staging, request)
        receipt_path = next(factory.remote.root.rglob("receipt.json"))
        os.chmod(receipt_path, 0o644)
        result = decode_remote_deletion_result(RemoteDeletionHelperExecutor(
            factory.staging, factory.remote, os.getuid(), clock=lambda: NOW
        ).execute(request.request_id, request.request_hash, CancellationToken()))
        self.assertEqual(result.outcome, RemoteDeletionOutcome.FAILED)
        self.assertEqual(result.error_code, "invalid_remote_backup_receipt")
        self.assertTrue(receipt_path.exists())
        factory.close()


class OpenSshRemoteDeletionTests(unittest.TestCase):
    def test_port_stages_bound_request_and_accepts_persisted_result(self):
        factory = _Factory()
        staging = _Staging()
        invoker = _Invoker(staging)
        port = OpenSshRemoteDeletionPort(
            staging, invoker, factory.remote, lambda _: "delete-remote-4",
            clock=lambda: NOW,
        )
        port.delete(factory.manifest, CancellationToken())
        request = decode_remote_deletion_request(
            staging.uploads[0][1], expected_hash=invoker.calls[0][1], now=NOW
        )
        self.assertEqual(request.remote_receipt_hash, factory.receipt.receipt_hash)
        self.assertEqual(request.key_reference, factory.receipt.key_reference)
        factory.close()

    def test_ambiguous_invoke_reads_result_and_tamper_fails_closed(self):
        factory = _Factory()
        staging = _Staging()
        invoker = _Invoker(staging, error=AdapterError("remote_deletion_timeout", "x"))
        port = OpenSshRemoteDeletionPort(
            staging, invoker, factory.remote, lambda _: "delete-remote-5",
            clock=lambda: NOW,
        )
        port.delete(factory.manifest, CancellationToken())
        decoded = decode_remote_deletion_result(staging.result)
        staging.result = encode_remote_deletion_result(
            replace(decoded, manifest_hash="f" * 64, result_hash="").with_hash()
        )
        invoker.write_result = False
        with self.assertRaises(AdapterError):
            port.delete(factory.manifest, CancellationToken())
        factory.close()

    def test_root_invoker_uses_fixed_passwordless_helper_command(self):
        runner, gate = _Runner(), _Gate()
        invoker = OpenSshRemoteDeletionInvoker(
            "development", runner, gate, control_socket="/tmp/cm"
        )
        invoker.invoke("delete-1", "a" * 64, CancellationToken())
        self.assertEqual(gate.calls, 1)
        self.assertEqual(runner.requests[0].argv[-1],
                         "sudo -n -- /usr/bin/llm-manager-remote-helper "
                         "invoke-deletion delete-1 " + "a" * 64)


class _Factory:
    def __init__(self, protected=False):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        target = root / "target"
        target.write_bytes(b"before")
        changes = ChangeSet(
            "changes", "ssh:host",
            (Change("change", str(target), ChangeOperation.REPLACE_FILE,
                    "before", "after", None, "diff"),), "c" * 64,
        )
        local = LocalBackupStore(root / "local", (root,))
        self.manifest = local.create(BackupRequest(
            "backup-1", "plan-1", "ssh:host", "SHA256:" + "a" * 43,
            changes, EncryptionInfo(enabled=False),
        ), CancellationToken())
        self.remote = SandboxRemoteRecoveryStore(
            root / "remote", AesGcmBackupCipher(_Keys()), "remote-master-v1",
            sandbox=True,
        )
        self.receipt = self.remote.create(
            self.manifest, local.restore_items(self.manifest, CancellationToken()),
            CancellationToken(),
        )
        if protected:
            self.remote.set_protected(self.manifest, True)
        self.staging = root / "staging"
        self.staging.mkdir(mode=0o700)

    def close(self):
        self.temp.cleanup()


def _stage(root, request):
    operation = root / request.request_id / request.request_hash
    (operation / "items").mkdir(parents=True)
    for path in (root, operation.parent, operation, operation / "items"):
        os.chmod(path, 0o700)
    path = operation / "request.json"
    path.write_bytes(encode_remote_deletion_request(request))
    os.chmod(path, 0o600)
    return operation


class _Staging:
    def __init__(self):
        self.uploads, self.result = [], b""

    def prepare_private_directory(self, path):
        self.path = path

    def upload_private_file(self, path, content):
        self.uploads.append((path, content))

    def read_private_file(self, path, max_bytes):
        return self.result


class _Invoker:
    def __init__(self, staging, error=None):
        self.staging, self.error, self.calls, self.write_result = staging, error, [], True

    def invoke(self, request_id, request_hash, cancellation):
        self.calls.append((request_id, request_hash))
        if self.write_result:
            request = decode_remote_deletion_request(
                self.staging.uploads[-1][1], expected_hash=request_hash, now=NOW
            )
            self.staging.result = encode_remote_deletion_result(RemoteDeletionResult(
                "1.0", request_id, request_hash, request.backup_id, request.host_id,
                request.host_fingerprint, request.manifest_hash,
                request.remote_receipt_hash, request.key_reference,
                RemoteDeletionOutcome.DELETED, None, NOW,
            ).with_hash())
        if self.error:
            raise self.error


class _Runner:
    def __init__(self):
        self.requests = []

    def run(self, request, cancellation):
        self.requests.append(request)
        return CommandResult(("ssh",), 0, "", "", False, 1)


class _Gate:
    def __init__(self):
        self.calls = 0

    def assert_ready(self, cancellation):
        self.calls += 1


class _Keys:
    def get_key(self, key_reference, key_scope):
        return b"r" * 32


if __name__ == "__main__":
    unittest.main()
