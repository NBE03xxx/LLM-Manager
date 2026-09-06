import io
import json
import unittest
from contextlib import contextmanager, redirect_stdout
from datetime import timedelta
from unittest.mock import patch

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.infrastructure import root_restore_review_cli as cli
from llm_manager.infrastructure.root_restore_review import RestoreCaller
from llm_manager.infrastructure.root_restore_store import RootRestoreState
from tests import test_root_restore_store as fixture
from tests.test_local_root_restore_protocol import NOW


class RootRestoreStatusTests(unittest.TestCase):
    setUp = fixture.RootRestoreStoreTests.setUp
    begin = fixture.RootRestoreStoreTests.begin

    def read(self, **overrides):
        args = dict(expected_hash=self.request.request_hash, caller_uid=1000,
                    host_id=self.request.host_id, cancellation=self.token)
        args.update(overrides)
        return self.store.reconcile(self.request.request_id, **args)

    def invoke(self, args=None, caller=None):
        @contextmanager
        def factory():
            yield self.store
        output = io.StringIO()
        with patch.object(cli, 'production_status', factory), patch.object(cli, 'production_review') as mutation, patch.object(cli, 'resolve_restore_caller', return_value=caller or RestoreCaller(1000, self.request.host_id)), redirect_stdout(output):
            code = cli.main(args or ['status', self.request.request_id, self.request.request_hash])
            mutation.assert_not_called()
        return code, json.loads(output.getvalue())

    def snapshot(self):
        return {p.name: p.read_bytes() for p in self.root.iterdir()}

    def test_review_only_is_readable_after_expiry_without_creating_attempt(self):
        before = self.snapshot()
        self.now = NOW + timedelta(days=1)
        code, result = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(result['state'], 'review_only')
        self.assertIsNone(result['attempt'])
        self.assertIsNone(result['result'])
        self.assertEqual(self.snapshot(), before)
        with self.assertRaises(AdapterError): self.begin()

    def test_attempt_only_is_unknown_and_never_retried(self):
        self.begin()
        before = self.snapshot()
        code, result = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(result['state'], 'unknown')
        self.assertTrue(result['requires_attention'])
        self.assertIsNotNone(result['attempt'])
        self.assertIsNone(result['result'])
        self.assertEqual(self.snapshot(), before)
        with self.assertRaises(AdapterError): self.begin()

    def test_terminal_history_is_bound_and_readable_after_expiry(self):
        attempt = self.begin()
        saved = self.store.finish(attempt, RootRestoreState.COMMITTED, None, self.token)
        self.now = NOW + timedelta(days=1)
        self.assertEqual(self.read().result, saved)
        code, result = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(result['state'], 'committed')
        self.assertFalse(result['requires_attention'])
        self.assertEqual(result['request_hash'], saved.request_hash)

    def test_wrong_caller_host_hash_and_bool_uid_are_rejected(self):
        for override in ({'caller_uid': 1001}, {'caller_uid': True}, {'caller_uid': 0},
                         {'host_id': 'local:other'}, {'expected_hash': 'f'*64}, {'expected_hash': 'bad'}):
            with self.subTest(override=override), self.assertRaises(AdapterError):
                self.read(**override)
        code, result = self.invoke(caller=RestoreCaller(1001, self.request.host_id))
        self.assertEqual(code, 1)
        self.assertNotIn('attempt', result)

    def test_missing_pending_or_tampered_evidence_is_not_review_only(self):
        path = self.root / (self.request.request_id + '.review.json')
        content = path.read_bytes()
        path.write_bytes(content + b'\n')
        self.assertEqual(self.invoke()[0], 1)
        path.write_bytes(content)
        pending = self.root / (self.request.request_id + '.attempt.json.pending')
        pending.write_bytes(b'partial')
        self.assertEqual(self.invoke()[0], 1)
        pending.unlink()
        path.unlink()
        self.assertEqual(self.invoke()[0], 1)

    def test_cancel_and_store_writer_contention_reject_status(self):
        with self.store._lock(self.request.request_id, self.token, write=True):
            with self.assertRaises(AdapterError): self.read()
        self.token.cancel()
        with self.assertRaises(OperationCancelled): self.read()

    def test_invalid_arguments_and_nonroot_never_open_store(self):
        for args in (['status', '../escape', 'a'*64], ['status', 'id', 'bad']):
            with patch.object(cli, 'resolve_restore_caller', return_value=RestoreCaller(1000, self.request.host_id)), patch.object(cli, 'production_status') as factory, redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(args), 1)
                factory.assert_not_called()
        with patch('os.geteuid', return_value=1000), patch.object(cli, 'production_status') as factory, redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['status', 'id', 'a'*64]), 1)
            factory.assert_not_called()

    def test_status_composition_only_opens_execution_store_and_closes_fd(self):
        with patch.object(cli, 'open_production_execution_directory', return_value=101), patch.object(cli.os, 'close') as close, patch.object(cli, 'open_production_key_directory') as keys, patch.object(cli, 'open_production_directory') as origins, patch.object(cli, 'open_production_source_parent') as target:
            with cli.production_status() as store:
                self.assertEqual(store.fd, 101)
            close.assert_called_once_with(101)
            keys.assert_not_called()
            origins.assert_not_called()
            target.assert_not_called()
