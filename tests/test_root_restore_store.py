import json
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.infrastructure.local_root_restore_preflight import RootRestoreReviewEvidence
from llm_manager.infrastructure.root_restore_store import RootRestoreStore, RootRestoreState, _wrap
from tests.test_local_root_restore_protocol import request, NOW


class RootRestoreStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        self.now = NOW
        self.options = dict(owner_uid=os.getuid(), owner_gid=os.getgid(), clock=lambda: self.now)
        self.store = RootRestoreStore(self.fd, **self.options)
        self.request = request()
        self.review = RootRestoreReviewEvidence(self.request, NOW, NOW + timedelta(minutes=2), 'a' * 64, 'b' * 64)
        self.token = CancellationToken()
        self.store.save_review(self.review, self.token)

    def begin(self, intent=None):
        intent = intent or self.request
        return self.store.begin(intent, expected_hash=intent.request_hash, caller_uid=1000,
                                host_id=intent.host_id, cancellation=self.token)

    def test_review_reload_and_attempt_only_survive_reopening(self):
        self.assertEqual(self.store.load_review(self.request.request_id, self.token), self.review)
        self.assertTrue(self.store.request_is_unused(self.request.request_id, self.token))
        attempt = self.begin()
        other = RootRestoreStore(self.fd, **self.options)
        view = other.load_execution(self.request.request_id, self.token)
        self.assertEqual(view.attempt, attempt)
        self.assertIsNone(view.result)
        self.assertTrue(view.requires_attention)
        self.assertFalse(other.request_is_unused(self.request.request_id, self.token))

    def test_committed_failed_unknown_results_are_immutable_and_bound(self):
        for state, code in ((RootRestoreState.COMMITTED, None), (RootRestoreState.FAILED, 'validation_failed'),
                            (RootRestoreState.UNKNOWN, 'connection_lost')):
            intent = replace(self.request, request_id='restore-' + state.value).with_hash()
            self.store.save_review(replace(self.review, approved_request=intent), self.token)
            attempt = self.begin(intent)
            result = self.store.finish(attempt, state, code, self.token)
            view = self.store.load_execution(intent.request_id, self.token)
            self.assertEqual(view.result, result)
            self.assertEqual(view.requires_attention, state is not RootRestoreState.COMMITTED)
            with self.assertRaises(AdapterError): self.store.finish(attempt, state, code, self.token)
            with self.assertRaises(AdapterError): self.begin(intent)

    def test_rehashed_same_id_request_and_duplicate_review_cannot_replace_original(self):
        with self.assertRaises(AdapterError): self.store.save_review(self.review, self.token)
        changed = replace(self.request, approval_id='other').with_hash()
        with self.assertRaises(AdapterError): self.begin(changed)
        self.assertTrue(self.store.request_is_unused(self.request.request_id, self.token))

    def test_expired_review_blocks_begin_but_execution_history_remains_readable(self):
        attempt = self.begin()
        self.now = NOW + timedelta(minutes=10)
        with self.assertRaises(AdapterError): self.store.load_review(self.request.request_id, self.token)
        with self.assertRaises(AdapterError): self.begin()
        self.assertEqual(self.store.load_execution(self.request.request_id, self.token).attempt, attempt)
        self.store.finish(attempt, RootRestoreState.UNKNOWN, 'late_result', self.token)
        self.assertFalse(self.store.request_is_unused(self.request.request_id, self.token))

    def test_tampered_review_and_symlink_attempt_never_report_unused(self):
        path = self.root / (self.request.request_id + '.review.json')
        saved = path.read_bytes()
        path.write_bytes(saved + b'\n')
        with self.assertRaises(AdapterError): self.store.request_is_unused(self.request.request_id, self.token)
        path.write_bytes(saved)
        (self.root / (self.request.request_id + '.attempt.json')).symlink_to(path)
        with self.assertRaises(AdapterError): self.store.request_is_unused(self.request.request_id, self.token)

    def test_orphan_result_is_rejected(self):
        attempt = self.begin()
        self.store.finish(attempt, RootRestoreState.UNKNOWN, 'unknown', self.token)
        (self.root / (self.request.request_id + '.attempt.json')).unlink()
        with self.assertRaises(AdapterError): self.store.load_execution(self.request.request_id, self.token)

    def test_attempt_save_failure_leaves_attention_evidence_and_blocks_retry(self):
        with patch('os.fsync', side_effect=OSError('injected')), self.assertRaises(AdapterError): self.begin()
        self.assertTrue(any(name.endswith('.pending') for name in os.listdir(self.fd)))
        with self.assertRaises(AdapterError): self.begin()
        with self.assertRaises(AdapterError): self.store.request_is_unused(self.request.request_id, self.token)

    def test_result_failure_keeps_attempt_and_does_not_allow_retry(self):
        attempt = self.begin()
        with patch('os.fsync', side_effect=OSError('injected')), self.assertRaises(AdapterError):
            self.store.finish(attempt, RootRestoreState.COMMITTED, None, self.token)
        self.assertTrue((self.root / (self.request.request_id + '.attempt.json')).exists())
        with self.assertRaises(AdapterError): self.begin()

    def test_cancel_does_not_consume_request(self):
        self.token.cancel()
        with self.assertRaises(OperationCancelled): self.begin()
        self.token = CancellationToken()
        self.assertTrue(self.store.request_is_unused(self.request.request_id, self.token))

    def test_wrong_result_binding_state_and_error_are_not_saved(self):
        attempt = self.begin()
        with self.assertRaises(AdapterError):
            self.store.finish(replace(attempt, request_hash='f' * 64), RootRestoreState.COMMITTED, None, self.token)
        for state, code in ((RootRestoreState.COMMITTED, 'error'), (RootRestoreState.FAILED, None),
                            (RootRestoreState.UNKNOWN, 'secret text!'), ('committed', None)):
            with self.subTest(state=state, code=code), self.assertRaises(AdapterError):
                self.store.finish(attempt, state, code, self.token)
        self.assertIsNone(self.store.load_execution(self.request.request_id, self.token).result)

    def test_reader_sharing_fd_cannot_observe_write_in_progress(self):
        original = self.store._publish
        def inspect(*args):
            with self.assertRaises(AdapterError) as caught:
                self.store.request_is_unused(self.request.request_id, self.token)
            self.assertEqual(caught.exception.code, 'root_restore_store_busy')
            return original(*args)
        with patch.object(self.store, '_publish', side_effect=inspect): self.begin()

    def test_rehashed_attempt_cannot_reference_another_review(self):
        attempt = self.begin()
        path = self.root / (self.request.request_id + '.attempt.json')
        path.write_bytes(_wrap('attempt', replace(attempt, review_hash='f' * 64)))
        with self.assertRaises(AdapterError):
            self.store.request_is_unused(self.request.request_id, self.token)

    def test_directory_fsync_failure_after_attempt_publication_still_blocks_replay(self):
        original = os.fsync
        count = 0
        def fail_directory(fd):
            nonlocal count
            count += 1
            if count == 2: raise OSError('directory fsync failed')
            return original(fd)
        with patch('os.fsync', side_effect=fail_directory), self.assertRaises(AdapterError):
            self.begin()
        self.assertFalse(self.store.request_is_unused(self.request.request_id, self.token))
        with self.assertRaises(AdapterError): self.begin()
