from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from io import BytesIO
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher
from llm_manager.infrastructure.remote_backup import SandboxRemoteRecoveryStore
from llm_manager.infrastructure.remote_helper import (
    REMOTE_HELPER_OPERATION, REMOTE_HELPER_PROTOCOL_VERSION,
    RemoteRecoveryRequest, encode_remote_request,
)
from llm_manager.infrastructure.remote_helper_cli import main, run_remote_helper
from llm_manager.infrastructure.journal import JournalStatus, JournalTarget
from llm_manager.infrastructure.remote_journal import RemoteJournalEvidence, encode_remote_journal_evidence
from llm_manager.infrastructure.remote_retention import (
    REMOTE_RETENTION_OPERATION,
    REMOTE_RETENTION_PROTOCOL_VERSION,
    RemoteRetentionRequest,
    decode_remote_retention_result,
    encode_remote_retention_request,
)


NOW = datetime.now(UTC)


class RemoteHelperCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir()
        self.uid = os.getuid()
        if self.uid == 0:
            self.uid = 1000
        self.backup = SandboxRemoteRecoveryStore(
            Path(self.temp.name) / "remote", AesGcmBackupCipher(_Keys()),
            "remote-master-v1", sandbox=True,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_user_prepare_root_invoke_and_user_cleanup_fixed_flow(self):
        request = _request()
        relative = f".local/state/llm-manager/remote-helper/{request.request_id}/{request.request_hash}"
        code, _ = run_remote_helper(
            ("user-stage-prepare", relative), effective_uid=self.uid, current_uid=self.uid,
            home_for_uid=lambda _: self.home,
        )
        self.assertEqual(code, 0)
        directory = self.home / relative
        self._write(directory / "request.json", encode_remote_request(request))
        self._write(directory / "items" / f"0000-{request.item_hashes[0][1]}.bin", b"before")
        code, result = run_remote_helper(
            ("invoke-recovery", request.request_id, request.request_hash),
            environ={"SUDO_UID": str(self.uid)}, effective_uid=0, current_uid=0,
            home_for_uid=lambda _: self.home, backend=self.backup,
        )
        self.assertEqual(code, 0)
        self.assertIn(b'"success":true', result)
        self.assertTrue((directory / "result.json").is_file())
        code, _ = run_remote_helper(
            ("user-stage-remove", relative), effective_uid=self.uid, current_uid=self.uid,
            home_for_uid=lambda _: self.home,
        )
        self.assertEqual(code, 0)
        self.assertFalse(directory.exists())

    def test_rejects_privilege_path_uid_unknown_command_and_unsafe_cleanup(self):
        request = _request()
        relative = f".local/state/llm-manager/remote-helper/{request.request_id}/{request.request_hash}"
        cases = (
            (("user-stage-prepare", relative), {"effective_uid": 0, "current_uid": 0}),
            (("user-stage-prepare", "../escape"), {"effective_uid": self.uid, "current_uid": self.uid}),
            (("invoke-recovery", request.request_id, request.request_hash), {"effective_uid": self.uid, "current_uid": self.uid}),
            (("invoke-recovery", request.request_id, request.request_hash), {"effective_uid": 0, "current_uid": 0, "environ": {}}),
            (("shell", "id"), {"effective_uid": self.uid, "current_uid": self.uid}),
        )
        for argv, kwargs in cases:
            with self.subTest(argv=argv):
                code, result = run_remote_helper(argv, home_for_uid=lambda _: self.home, backend=self.backup, **kwargs)
                self.assertEqual(code, 1)
                self.assertIn(b'"success":false', result)
        run_remote_helper(
            ("user-stage-prepare", relative), effective_uid=self.uid, current_uid=self.uid,
            home_for_uid=lambda _: self.home,
        )
        directory = self.home / relative
        (directory / "unexpected").write_text("unsafe")
        code, _ = run_remote_helper(
            ("user-stage-remove", relative), effective_uid=self.uid, current_uid=self.uid,
            home_for_uid=lambda _: self.home,
        )
        self.assertEqual(code, 1)
        self.assertTrue(directory.exists())

    def test_isolated_main_builds_backend_only_for_root_operation(self):
        output = BytesIO()
        factories = []
        code = main(
            ["unknown"], stdout=output,
            backend_factory=lambda: factories.append(True),
            effective_uid=self.uid, current_uid=self.uid,
            home_for_uid=lambda _: self.home,
        )
        self.assertEqual(code, 1)
        self.assertEqual(factories, [])
        output = BytesIO()
        code = main(
            ["invoke-recovery", "backup", "a" * 64], stdout=output,
            backend_factory=lambda: (_ for _ in ()).throw(AdapterError("key_failed", "fail")),
            environ={"SUDO_UID": str(self.uid)}, effective_uid=0, current_uid=0,
            home_for_uid=lambda _: self.home,
        )
        self.assertEqual(code, 1)
        self.assertEqual(output.getvalue(), b'{"code":"remote_backend_unavailable","success":false}\n')

    def test_root_journal_command_returns_only_bound_canonical_evidence(self):
        evidence = RemoteJournalEvidence(
            "1.0", "operation-1", "plan-1", "ssh:host", "SHA256:" + "f" * 43,
            "c" * 64, "backup-1", "d" * 64, "a" * 64, None,
            JournalStatus.APPLYING,
            (JournalTarget("/etc/example", "b" * 64, "e" * 64),), "f" * 64,
        ).with_hash()
        content = encode_remote_journal_evidence(evidence)
        loader = _JournalLoader(content)
        code, result = run_remote_helper(
            ("read-journal-evidence", "operation-1", "a" * 64),
            effective_uid=0, current_uid=0, journal_loader=loader,
        )
        self.assertEqual((code, result), (0, content))
        self.assertEqual(loader.calls, [("operation-1", "a" * 64)])
        code, result = run_remote_helper(
            ("read-journal-evidence", "../bad", "a" * 64),
            effective_uid=0, current_uid=0, journal_loader=loader,
        )
        self.assertEqual(code, 1)
        self.assertIn(b"invalid_remote_journal_identity", result)

    def test_root_retention_command_reads_fixed_staging_and_persists_result(self):
        request = RemoteRetentionRequest(
            "1.0", REMOTE_RETENTION_PROTOCOL_VERSION, REMOTE_RETENTION_OPERATION,
            "retention-1", "ssh:gpu-box", "SHA256:" + "a" * 43,
            NOW, NOW, NOW + timedelta(minutes=5),
        ).with_hash()
        relative = f".local/state/llm-manager/remote-helper/{request.request_id}/{request.request_hash}"
        code, _ = run_remote_helper(
            ("user-stage-prepare", relative), effective_uid=self.uid, current_uid=self.uid,
            home_for_uid=lambda _: self.home,
        )
        self.assertEqual(code, 0)
        self._write(self.home / relative / "request.json", encode_remote_retention_request(request))
        backend = _RetentionBackend()
        code, result = run_remote_helper(
            ("invoke-retention", request.request_id, request.request_hash),
            environ={"SUDO_UID": str(self.uid)}, effective_uid=0, current_uid=0,
            home_for_uid=lambda _: self.home, backend=backend,
        )
        self.assertEqual(code, 0)
        decoded = decode_remote_retention_result(result)
        self.assertEqual(decoded.host_fingerprint, request.host_fingerprint)
        self.assertEqual(backend.keep_generations, 10)
        self.assertEqual((self.home / relative / "result.json").read_bytes(), result)

    def test_remote_wrapper_is_isolated_and_not_installed_by_local_package(self):
        project = Path(__file__).resolve().parents[1]
        wrapper = project / "packaging/remote/bin/llm-manager-remote-helper"
        self.assertEqual(wrapper.read_text().splitlines()[0], "#!/usr/bin/python3 -I")
        local_install = (project / "debian/llm-manager.install").read_text()
        self.assertNotIn("llm-manager-remote-helper", local_install)

    @staticmethod
    def _write(path, content):
        path.write_bytes(content)
        os.chmod(path, 0o600)


def _request():
    digest = hashlib.sha256(b"before").hexdigest()
    base = RemoteRecoveryRequest(
        REMOTE_HELPER_PROTOCOL_VERSION, REMOTE_HELPER_OPERATION, "backup-1", "backup-1",
        "plan-1", "c" * 64, "ssh:gpu-box", "SHA256:" + "a" * 43, "d" * 64,
        "/var/lib/llm-manager/backups/87fe234ee99a458ab8e75e14/backup-1",
        "remote-master-v1", "remote_root", (("/etc/example", digest),),
        NOW, NOW + timedelta(days=30), False, NOW, NOW + timedelta(minutes=5),
    )
    return base.with_hash()


class _Keys:
    def get_key(self, key_reference, key_scope):
        if (key_reference, key_scope) != ("remote-master-v1", "remote_root"):
            raise AdapterError("invalid_key", "unexpected key")
        return b"r" * 32


class _JournalLoader:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def load_journal_evidence(self, operation_id, request_hash, cancellation):
        self.calls.append((operation_id, request_hash))
        return self.content


class _RetentionBackend:
    key_reference = "remote-master-v1"

    def __init__(self):
        self.keep_generations = None

    def list_retention(self, host_id, *, expected_fingerprint=None):
        return ()

    def prune(self, host_id, *, now, keep_generations=10, expected_fingerprint=None):
        self.keep_generations = keep_generations
        return ()


if __name__ == "__main__":
    unittest.main()
