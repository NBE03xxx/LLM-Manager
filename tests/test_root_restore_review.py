import os
import unittest
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.infrastructure.local_root_restore_preflight import CheckLocalRootRestore
from llm_manager.infrastructure.local_root_restore_protocol import encode_request
from llm_manager.infrastructure.root_restore_execution import SingleRootRestoreTarget
from llm_manager.infrastructure.root_restore_review import ProduceRootRestoreReview, RestoreCaller, resolve_restore_caller
from tests import test_root_backup_verification as fixture
from tests.test_local_root_restore_protocol import NOW


class RootRestoreReviewTests(unittest.TestCase):
    setUp = fixture.RootBackupVerificationTests.setUp
    run_capture = fixture.RootBackupVerificationTests.run_capture
    prepare = fixture.RootBackupVerificationTests.prepare

    def make(self):
        self.record = self.prepare()
        self.backend = SingleRootRestoreTarget(self.source, owner_uid=os.getuid(), owner_gid=os.getgid())
        self.producer = ProduceRootRestoreReview(self.reader, self.cipher, self.backend, self.store,
            identity=lambda: RestoreCaller(1000, self.record.host_id), clock=lambda: NOW)
        self.token = CancellationToken()
        self.selection = self.producer.preview('backup-1', self.token)
        return self.selection.request('produced-1', 'approval-produced')

    def approve(self, intent):
        return self.producer.approve(encode_request(intent), intent.request_hash, self.token)

    def test_produced_review_passes_real_preflight_without_mutation(self):
        intent = self.make()
        review = self.approve(intent)
        self.assertEqual(review.origin_record_hash, self.record.record_hash)
        self.assertEqual(intent.manifest_hash, self.record.source_manifest_hash)
        self.assertEqual(self.store.load_review(intent.request_id, self.token), review)
        outcome = CheckLocalRootRestore(self.port, clock=lambda: NOW).execute(intent,
            expected_hash=intent.request_hash, caller_uid=1000, host_id=intent.host_id, cancellation=self.token)
        self.assertEqual(outcome.request_hash, intent.request_hash)
        self.assertEqual(self.target.read_bytes(), b'new current settings')
        self.assertTrue(self.store.request_is_unused(intent.request_id, self.token))

    def test_rehashed_untrusted_fields_rejected(self):
        intent = self.make()
        for fields in ({'manifest_hash': 'f'*64}, {'inventory_hash': 'f'*64},
                       {'preview_hash': 'f'*64}, {'caller_uid': 1001}, {'host_id': 'other'},
                       {'expires_at': NOW + timedelta(minutes=4)}):
            with self.subTest(fields=fields), self.assertRaises(AdapterError):
                self.approve(replace(intent, **fields).with_hash())
        self.assertFalse((self.root / 'executions' / (intent.request_id + '.review.json')).exists())

    def test_changed_target_rejects_previous_preview(self):
        intent = self.make()
        self.target.write_bytes(b'changed after preview')
        with self.assertRaises(AdapterError): self.approve(intent)
        self.assertFalse((self.root / 'executions' / (intent.request_id + '.review.json')).exists())

    def test_changed_payload_rejects_previous_preview(self):
        intent = self.make()
        (self.root / 'store/backup-1.bin').write_bytes(b'changed')
        with self.assertRaises(AdapterError): self.approve(intent)

    def test_expired_request_rejected(self):
        intent = self.make()
        self.producer.clock = lambda: NOW + timedelta(minutes=5)
        with self.assertRaises(AdapterError): self.approve(intent)

    def test_cancel_prevents_review_publication(self):
        intent = self.make()
        self.token = CancellationToken(cancelled=True)
        with self.assertRaises(OperationCancelled): self.approve(intent)
        self.assertFalse((self.root / 'executions' / (intent.request_id + '.review.json')).exists())

    def test_duplicate_review_rejected(self):
        intent = self.make()
        self.approve(intent)
        with self.assertRaises(AdapterError): self.approve(intent)

    def test_preview_rejects_wrong_host_and_no_change(self):
        self.make()
        self.producer.identity = lambda: RestoreCaller(1000, 'other')
        with self.assertRaises(AdapterError): self.producer.preview('backup-1', self.token)
        self.producer.identity = lambda: RestoreCaller(1000, self.record.host_id)
        self.target.write_bytes(self.original)
        with self.assertRaises(AdapterError): self.producer.preview('backup-1', self.token)

    def test_target_change_during_origin_recheck_rejected(self):
        self.make()
        read = self.reader.read
        def change(*args):
            result = read(*args)
            self.target.write_bytes(b'concurrent change')
            return result
        with patch.object(self.reader, 'read', side_effect=change), self.assertRaises(AdapterError):
            self.producer.preview('backup-1', self.token)


class RestoreCallerTests(unittest.TestCase):
    def test_root_entry_resolves_uid_and_local_host(self):
        with patch('os.geteuid', return_value=0), patch.dict(os.environ, {'PKEXEC_UID': '1000'}, clear=True), patch('os.uname', return_value=SimpleNamespace(nodename='machine')):
            self.assertEqual(resolve_restore_caller(), RestoreCaller(1000, 'local:machine'))

    def test_nonroot_cannot_claim_pkexec_identity(self):
        with patch('os.geteuid', return_value=1000), patch.dict(os.environ, {'PKEXEC_UID': '1000'}, clear=True), self.assertRaises(AdapterError):
            resolve_restore_caller()

    def test_invalid_uid_rejected(self):
        for uid in ('', '0', '-1', '01', ' 1000', '１０００', '4294967295', '99999999999'):
            with self.subTest(uid=uid), patch('os.geteuid', return_value=0), patch.dict(os.environ, {'PKEXEC_UID': uid}, clear=True), self.assertRaises(AdapterError):
                resolve_restore_caller()
