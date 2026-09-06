import hashlib
import os
import tempfile
import unittest
from contextlib import ExitStack
from dataclasses import replace
from functools import partial
from pathlib import Path
from unittest.mock import patch

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import utc_now
from llm_manager.infrastructure import root_apply_capture as capture_module
from llm_manager.infrastructure.helper_backend import LocalSystemHelperBackend
from llm_manager.infrastructure.helper_cli import run_helper
from llm_manager.infrastructure.helper_protocol import encode_request
from llm_manager.infrastructure.helper_receipts import HelperReceiptStore
from llm_manager.infrastructure.root_backup_capture import CaptureRootBackup, LocalRootBackupKeys, decrypt_root_backup
from llm_manager.infrastructure.root_backup_evidence import RootBackupEvidenceReader
from llm_manager.infrastructure.root_restore_setup_cli import initialize_empty_state
from llm_manager.infrastructure.root_target_lock import locked_root_target
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher
from llm_manager.planning.ollama import DROP_IN_PATH
from tests.test_helper_protocol import _request


class RootApplyCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.uid, self.gid = os.getuid(), os.getgid()
        self.options = dict(owner_uid=self.uid, owner_gid=self.gid)
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try: initialize_empty_state(fd, **self.options)
        finally: os.close(fd)
        self.state = self.root / 'local-root-restore'
        self.target = self.root / DROP_IN_PATH.lstrip('/')
        self.target.parent.mkdir(parents=True)
        self.target.parent.chmod(0o755)
        self.original = b'[Service]\nEnvironment="OLLAMA_FLASH_ATTENTION=0"\n'
        self.changed = b'[Service]\nEnvironment="OLLAMA_FLASH_ATTENTION=1"\n'
        self.target.write_bytes(self.original)
        self.target.chmod(0o644)
        request = _request(utc_now())
        operation = replace(request.operations[0], before_hash=hashlib.sha256(self.original).hexdigest(),
                            staged_content_hash=hashlib.sha256(self.changed).hexdigest())
        self.request = replace(request, host_id='local:' + os.uname().nodename,
                               operations=(operation,) + request.operations[1:], backup_id='backup-1',
                               approval_id='approval-1', manifest_hash='b' * 64).with_hash()
        self.runtime = self.root / 'run'
        self.calls = []
        self.backend = LocalSystemHelperBackend(root=self.root, sandbox=True,
                                               service_runner=lambda argv: self.calls.append(argv) or 0)
        self.receipts = HelperReceiptStore(self.root / 'receipts', sandbox=True)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in (
            ('open_production_key_directory', lambda: os.open(self.state / 'keys', os.O_RDONLY | os.O_DIRECTORY)),
            ('open_production_directory', lambda: os.open(self.state / 'backups', os.O_RDONLY | os.O_DIRECTORY)),
            ('LocalRootBackupKeys', partial(LocalRootBackupKeys, **self.options)),
            ('CaptureRootBackup', partial(CaptureRootBackup, **self.options)),
        ):
            self.stack.enter_context(patch.object(capture_module, name, value))
        self.stack.enter_context(patch('llm_manager.infrastructure.helper_cli.LocalSystemHelperBackend', return_value=self.backend))
        self.stack.enter_context(patch('os.geteuid', return_value=0))

    def run_apply(self):
        stage = self.runtime / str(self.uid) / 'llm-manager/helper'
        path = stage / self.request.operation_id
        path.mkdir(parents=True, exist_ok=True)
        stage.chmod(0o700); path.chmod(0o700)
        for name, content in (('request.json', encode_request(self.request)), ('write-1.content', self.changed)):
            item = path / name; item.write_bytes(content); item.chmod(0o600)
        return run_helper(self.request.operation_id, self.request.request_hash,
                          environ={'PKEXEC_UID': str(self.uid)}, runtime_base=self.runtime,
                          receipts=self.receipts, effective_uid=0)

    def test_authenticated_entry_captures_original_before_write_and_blocks_replay(self):
        write = self.backend.atomic_write
        def inspect(*args):
            fd = os.open(self.state / 'backups', os.O_RDONLY | os.O_DIRECTORY)
            key_fd = os.open(self.state / 'keys', os.O_RDONLY | os.O_DIRECTORY)
            try:
                reader = RootBackupEvidenceReader(fd, **self.options)
                record, envelope = reader.inspect('backup-1', CancellationToken())
                cipher = AesGcmBackupCipher(LocalRootBackupKeys(key_fd, **self.options))
                self.assertEqual(decrypt_root_backup(record, envelope, cipher), self.original)
                self.assertEqual(record.source_apply_request_hash, self.request.request_hash)
            finally: os.close(fd); os.close(key_fd)
            return write(*args)
        with patch.object(self.backend, 'atomic_write', side_effect=inspect):
            results = self.run_apply()
        self.assertTrue(all(item.completed for item in results))
        self.assertEqual(self.target.read_bytes(), self.changed)
        self.assertEqual(len(self.calls), 2)
        with self.assertRaises(AdapterError): self.run_apply()
        self.assertEqual(len(self.calls), 2)

    def test_capture_and_service_share_the_same_target_lock(self):
        publish = CaptureRootBackup._publish
        def locked():
            fd = os.open(self.target.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaises(AdapterError):
                    with locked_root_target(fd): pass
            finally: os.close(fd)
        def inspect(instance, *args):
            locked()
            return publish(instance, *args)
        self.backend.service_runner = lambda argv: locked() or 0
        with patch.object(CaptureRootBackup, '_publish', inspect):
            self.assertTrue(all(item.completed for item in self.run_apply()))

    def test_missing_key_refuses_even_absent_target_without_automatic_setup(self):
        for path in (self.state / 'keys').iterdir(): path.unlink()
        self.target.unlink()
        self.request = replace(self.request, operations=(replace(self.request.operations[0], before_hash=None),)
                               + self.request.operations[1:]).with_hash()
        results = self.run_apply()
        self.assertFalse(results[0].completed)
        self.assertFalse(self.target.exists())
        self.assertEqual(list((self.state / 'keys').iterdir()), [])
        self.assertEqual(list((self.state / 'backups').iterdir()), [])
        self.assertEqual(self.calls, [])

    def test_capture_failure_preserves_target_and_partial_evidence_without_retry(self):
        publish = CaptureRootBackup._publish
        def fail(instance, name, *args):
            if name.endswith('.json'): raise OSError('injected')
            return publish(instance, name, *args)
        with patch.object(CaptureRootBackup, '_publish', fail): results = self.run_apply()
        self.assertEqual(results[0].error_code, 'root_backup_capture_incomplete')
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(self.calls, [])
        self.assertEqual([p.name for p in (self.state / 'backups').iterdir()], ['backup-1.bin'])
        with self.assertRaises(AdapterError): self.run_apply()

    def test_wrong_host_missing_binding_or_service_before_write_rejected_before_receipt(self):
        original = self.request
        for request in (replace(original, host_id='local:other'),
                        replace(original, backup_id=None, approval_id=None, manifest_hash=None),
                        replace(original, operations=original.operations[1:] + original.operations[:1])):
            self.request = request.with_hash()
            with self.assertRaises(AdapterError): self.run_apply()
            self.assertFalse(self.receipts.root.exists())
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(self.calls, [])

    def test_expiry_after_capture_prevents_write_and_retains_backup(self):
        capture = capture_module.capture_before_replace
        def expire(request, fd):
            capture(request, fd)
            self.stack.enter_context(patch('llm_manager.infrastructure.helper_executor.utc_now',
                                           return_value=request.expires_at))
        with patch('llm_manager.infrastructure.helper_cli.capture_before_replace', side_effect=expire):
            results = self.run_apply()
        self.assertEqual(results[0].error_code, 'expired_request')
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertTrue((self.state / 'backups/backup-1.json').exists())
        self.assertEqual(self.calls, [])

    def test_invalid_staging_never_publishes_backup(self):
        self.changed = b'tampered staging'
        results = self.run_apply()
        self.assertFalse(results[0].completed)
        self.assertEqual(list((self.state / 'backups').iterdir()), [])
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(self.calls, [])

    def test_rollback_uses_existing_path_without_recapturing_or_requiring_key(self):
        from llm_manager.infrastructure.helper_protocol import HelperOperationKind
        for path in (self.state / 'keys').iterdir(): path.unlink()
        self.request = replace(self.request, operations=(
            replace(self.request.operations[0], kind=HelperOperationKind.RESTORE_FILE),
        ) + self.request.operations[1:]).with_hash()
        with patch('llm_manager.infrastructure.helper_cli.capture_before_replace') as capture:
            self.assertTrue(all(item.completed for item in self.run_apply()))
            capture.assert_not_called()
        self.assertEqual(list((self.state / 'backups').iterdir()), [])
