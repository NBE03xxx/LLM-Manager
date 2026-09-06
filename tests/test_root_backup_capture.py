import fcntl
import hashlib
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher
from llm_manager.infrastructure.root_backup_capture import CaptureRootBackup, LocalRootBackupKeys, decrypt_root_backup
from llm_manager.infrastructure.root_backup_evidence import RootBackupEvidenceReader
from tests.test_helper_protocol import _request
from tests.test_local_root_restore_protocol import NOW


class RootBackupCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fds = []
        for name in ('store', 'source', 'keys'):
            path = self.root / name
            path.mkdir(mode=0o700)
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
            self.fds.append(fd)
            self.addCleanup(os.close, fd)
        self.store, self.source, self.keys = self.fds
        self.original = b'[Service]\nEnvironment="OLLAMA_FLASH_ATTENTION=0"\n'
        self.target = self.root / 'source/90-llm-manager.conf'
        self.target.write_bytes(self.original)
        self.target.chmod(0o644)
        key = self.root / 'keys/key-1.key'
        key.write_bytes(os.urandom(32))
        key.chmod(0o600)
        ready = self.root / 'keys/key-1.ready'
        ready.write_bytes(hashlib.sha256(key.read_bytes()).hexdigest().encode('ascii'))
        ready.chmod(0o600)
        options = dict(owner_uid=os.getuid(), owner_gid=os.getgid())
        self.provider = LocalRootBackupKeys(self.keys, **options)
        self.cipher = AesGcmBackupCipher(self.provider)
        self.capture = CaptureRootBackup(self.store, self.source, self.cipher, clock=lambda: NOW, **options)
        self.reader = RootBackupEvidenceReader(self.store, **options)
        request = _request(NOW)
        op = replace(request.operations[0], before_hash=hashlib.sha256(self.original).hexdigest())
        self.request = replace(request, operations=(op,) + request.operations[1:], backup_id='backup-1',
                               approval_id='approval-1', manifest_hash='b' * 64).with_hash()

    def run_capture(self, token=None):
        return self.capture.execute(self.request, expected_hash=self.request.request_hash,
                                    key_id='key-1', cancellation=token or CancellationToken())

    def test_captures_original_encrypts_and_publishes_readable_evidence(self):
        record = self.run_capture()
        observed, envelope = self.reader.read('backup-1', record.record_hash, CancellationToken())
        self.assertEqual(record, observed)
        self.assertEqual(decrypt_root_backup(record, envelope, self.cipher), self.original)
        self.assertNotIn(self.original, envelope)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(sorted(os.listdir(self.store)), ['backup-1.bin', 'backup-1.json'])
        for path in (self.root / 'store').iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.stat().st_nlink, 1)

    def test_absent_target_produces_only_absence_record(self):
        self.target.unlink()
        op = replace(self.request.operations[0], before_hash=None)
        self.request = replace(self.request, operations=(op,) + self.request.operations[1:]).with_hash()
        record = self.run_capture()
        self.assertFalse(record.original.exists)
        self.assertEqual(os.listdir(self.store), ['backup-1.json'])
        self.assertEqual(self.reader.read('backup-1', record.record_hash, CancellationToken()), (record, None))

    def test_missing_wrong_scope_and_unsafe_key_never_fall_back_to_plaintext(self):
        with self.assertRaises(AdapterError): self.provider.get_key('key-1', 'remote_root')
        key = self.root / 'keys/key-1.key'
        for kind in ('mode', 'size', 'missing'):
            if kind == 'mode': key.chmod(0o644)
            elif kind == 'size':
                key.chmod(0o600)
                key.write_bytes(b'short')
            else: key.unlink()
            with self.subTest(kind=kind), self.assertRaises(AdapterError): self.run_capture()
            self.assertEqual(os.listdir(self.store), [])

    def test_replay_and_interrupted_staging_are_not_overwritten(self):
        self.run_capture()
        before = {p.name: p.read_bytes() for p in (self.root / 'store').iterdir()}
        with self.assertRaises(AdapterError): self.run_capture()
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root / 'store').iterdir()})

    def test_source_changed_during_encryption_is_rejected(self):
        encrypt = self.cipher.encrypt
        def change(*args, **kwargs):
            value = encrypt(*args, **kwargs)
            self.target.write_bytes(b'changed')
            return value
        with patch.object(self.cipher, 'encrypt', side_effect=change), self.assertRaises(AdapterError): self.run_capture()
        self.assertEqual(os.listdir(self.store), [])

    def test_symlink_unsafe_mode_and_stale_source_are_rejected(self):
        self.target.chmod(0o666)
        with self.assertRaises(AdapterError): self.run_capture()
        self.target.chmod(0o644)
        self.target.write_bytes(b'changed')
        with self.assertRaises(AdapterError): self.run_capture()
        self.target.unlink()
        self.target.symlink_to(self.root / 'keys/key-1.key')
        with self.assertRaises(AdapterError): self.run_capture()
        self.assertEqual(os.listdir(self.store), [])

    def test_payload_fsync_failure_leaves_no_committed_marker_and_blocks_retry(self):
        with patch('os.fsync', side_effect=OSError('injected')), self.assertRaises(AdapterError): self.run_capture()
        self.assertFalse((self.root / 'store/backup-1.json').exists())
        self.assertTrue(any(name.endswith('.pending') for name in os.listdir(self.store)))
        with self.assertRaises(AdapterError): self.run_capture()

    def test_marker_failure_preserves_ciphertext_but_reader_cannot_accept_pair(self):
        publish = self.capture._publish
        def fail(name, content, cancellation):
            if name.endswith('.json'): raise OSError('injected')
            return publish(name, content, cancellation)
        with patch.object(self.capture, '_publish', side_effect=fail), self.assertRaises(AdapterError): self.run_capture()
        self.assertEqual(os.listdir(self.store), ['backup-1.bin'])
        with self.assertRaises(AdapterError): self.reader.read('backup-1', 'a' * 64, CancellationToken())
        with self.assertRaises(AdapterError): self.run_capture()

    def test_final_directory_fsync_failure_is_incomplete_even_if_pair_is_readable(self):
        fsync = os.fsync
        count = 0
        def fail_last(fd):
            nonlocal count
            count += 1
            if count == 4: raise OSError('injected final durability failure')
            return fsync(fd)
        with patch('os.fsync', side_effect=fail_last), self.assertRaises(AdapterError) as caught:
            self.run_capture()
        self.assertEqual(caught.exception.code, 'root_backup_capture_incomplete')
        self.assertTrue((self.root / 'store/backup-1.json').exists())
        with self.assertRaises(AdapterError): self.run_capture()

    def test_request_expiring_during_encryption_does_not_publish(self):
        encrypt = self.cipher.encrypt
        def expire(*args, **kwargs):
            result = encrypt(*args, **kwargs)
            self.capture.clock = lambda: self.request.expires_at
            return result
        with patch.object(self.cipher, 'encrypt', side_effect=expire), self.assertRaises(AdapterError):
            self.run_capture()
        self.assertEqual(os.listdir(self.store), [])

    def test_cancel_during_encryption_does_not_publish(self):
        token = CancellationToken()
        encrypt = self.cipher.encrypt
        def cancel(*args, **kwargs):
            result = encrypt(*args, **kwargs)
            token.cancel()
            return result
        with patch.object(self.cipher, 'encrypt', side_effect=cancel), self.assertRaises(OperationCancelled): self.run_capture(token)
        self.assertEqual(os.listdir(self.store), [])

    def test_busy_store_rejects_capture_and_read_without_waiting(self):
        independent = os.open(self.root / 'store', os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(independent, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(AdapterError): self.run_capture()
            with self.assertRaises(AdapterError): self.reader.read('backup-1', 'a' * 64, CancellationToken())
        finally: os.close(independent)

    def test_aead_binds_host_apply_origin_and_original_metadata(self):
        record = self.run_capture()
        _, envelope = self.reader.read('backup-1', record.record_hash, CancellationToken())
        for changes in ({'host_id': 'other'}, {'source_apply_request_hash': 'f' * 64},
                        {'original': replace(record.original, sha256='f' * 64)}):
            with self.subTest(changes=changes), self.assertRaises(AdapterError):
                decrypt_root_backup(replace(record, **changes).with_hash(), envelope, self.cipher)

    def test_reader_sharing_borrowed_fd_cannot_convert_writer_lock(self):
        encrypt = self.cipher.encrypt
        def check_lock(*args, **kwargs):
            with self.assertRaises(AdapterError) as caught:
                self.reader.read('backup-1', 'a' * 64, CancellationToken())
            self.assertEqual(caught.exception.code, 'root_backup_store_busy')
            return encrypt(*args, **kwargs)
        with patch.object(self.cipher, 'encrypt', side_effect=check_lock):
            self.run_capture()


if __name__ == '__main__': unittest.main()
