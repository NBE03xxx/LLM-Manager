import unittest
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.infrastructure.local_root_key_provisioning import ProvisionLocalRootKey
import os
from llm_manager.infrastructure.local_root_restore_preflight import CheckLocalRootRestore, RootRestoreReviewEvidence
from llm_manager.infrastructure.root_restore_store import RootRestoreStore
from llm_manager.infrastructure.root_backup_verification import VerifyRootBackupOrigin
from tests import test_root_backup_capture as capture_fixture
from tests.test_local_root_restore_protocol import request, NOW


class RootBackupVerificationTests(unittest.TestCase):
    setUp = capture_fixture.RootBackupCaptureTests.setUp
    run_capture = capture_fixture.RootBackupCaptureTests.run_capture

    def prepare(self):
        for name in ('key-1.key', 'key-1.ready'):
            (self.root / 'keys' / name).unlink()
        ProvisionLocalRootKey(self.keys, owner_uid=os.getuid(), owner_gid=os.getgid()).execute(
            'key-1', CancellationToken()
        )
        record = self.run_capture()
        self.target.write_bytes(b'new current settings')
        self.target.chmod(0o644)
        current, _, _ = self.capture._observe(CancellationToken())
        intent = replace(request(), host_id=record.host_id, manifest_hash=record.source_manifest_hash, current=current, backup=record.original).with_hash()
        self.review = RootRestoreReviewEvidence(intent, NOW, NOW + timedelta(minutes=2),
                                                record.record_hash, record.source_apply_request_hash)
        self.verifier = VerifyRootBackupOrigin(self.reader, self.cipher)
        directory = self.root / 'executions'
        directory.mkdir(mode=0o700)
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, fd)
        self.store = RootRestoreStore(fd, owner_uid=os.getuid(), owner_gid=os.getgid(), clock=lambda: NOW)
        self.store.save_review(self.review, CancellationToken())
        store, verifier, capture = self.store, self.verifier, self.capture
        class Port:
            def load_review(self, request_id, cancellation): return store.load_review(request_id, cancellation)
            def request_is_unused(self, request_id, cancellation): return store.request_is_unused(request_id, cancellation)
            def observe_target(self, target, cancellation): return capture._observe(cancellation)[0]
            def verify_backup(self, evidence, cancellation): return verifier.execute(evidence, cancellation)
        self.port = Port()
        return record

    def check(self):
        intent = self.review.approved_request
        return CheckLocalRootRestore(self.port, clock=lambda: NOW).execute(
            intent, expected_hash=intent.request_hash, caller_uid=1000, host_id=intent.host_id,
            cancellation=CancellationToken(),
        )

    def test_real_capture_key_read_decrypt_and_preflight_preserve_target(self):
        self.prepare()
        intent = self.review.approved_request
        result = self.check()
        self.assertEqual(result.request_hash, intent.request_hash)
        self.assertEqual(self.target.read_bytes(), b'new current settings')

    def test_root_origin_binding_mismatch_rejected(self):
        self.prepare()
        for fields in ({'origin_record_hash': 'f' * 64}, {'source_apply_request_hash': 'f' * 64},
                       {'origin_record_hash': None}):
            with self.subTest(fields=fields), self.assertRaises(AdapterError):
                self.verifier.execute(replace(self.review, **fields), CancellationToken())
        intent = replace(self.review.approved_request, host_id='other').with_hash()
        with self.assertRaises(AdapterError):
            self.verifier.execute(replace(self.review, approved_request=intent), CancellationToken())

    def test_manifest_binding_cannot_be_rehashed_away(self):
        from llm_manager.infrastructure.root_backup_capture import decrypt_root_backup
        record = self.prepare()
        intent = replace(self.review.approved_request, manifest_hash='f' * 64).with_hash()
        with self.assertRaises(AdapterError):
            self.verifier.execute(replace(self.review, approved_request=intent), CancellationToken())
        _, envelope = self.reader.read(record.backup_id, record.record_hash, CancellationToken())
        forged = replace(record, source_manifest_hash='f' * 64).with_hash()
        with self.assertRaises(AdapterError): decrypt_root_backup(forged, envelope, self.cipher)

    def test_payload_change_during_decryption_is_rejected(self):
        self.prepare()
        decrypt = self.cipher.decrypt
        def change(*args, **kwargs):
            plaintext = decrypt(*args, **kwargs)
            (self.root / 'store/backup-1.bin').write_bytes(b'changed')
            return plaintext
        with patch.object(self.cipher, 'decrypt', side_effect=change), self.assertRaises(AdapterError):
            self.verifier.execute(self.review, CancellationToken())

    def test_key_loss_and_cancel_do_not_change_target(self):
        self.prepare()
        with self.assertRaises(OperationCancelled):
            self.verifier.execute(self.review, CancellationToken(cancelled=True))
        (self.root / 'keys/key-1.key').unlink()
        with self.assertRaises(AdapterError): self.verifier.execute(self.review, CancellationToken())
        self.assertEqual(self.target.read_bytes(), b'new current settings')

    def test_persisted_attempt_blocks_repeated_preflight_without_mutation(self):
        self.prepare()
        self.check()
        intent = self.review.approved_request
        self.store.begin(intent, expected_hash=intent.request_hash, caller_uid=1000,
                         host_id=intent.host_id, cancellation=CancellationToken())
        with self.assertRaises(AdapterError): self.check()
        self.assertEqual(self.target.read_bytes(), b'new current settings')
