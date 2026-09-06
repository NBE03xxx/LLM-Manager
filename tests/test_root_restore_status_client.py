import io
import json
import unittest
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandResult
from llm_manager.domain.serialization import to_primitive
from llm_manager.infrastructure.root_restore_review_client import RootRestoreReviewClient, REVIEW_HELPER
from llm_manager.infrastructure.root_restore_store import RootRestoreAttempt, RootRestoreResult, RootRestoreState, _digest
from llm_manager.infrastructure.root_restore_review import RestoreCaller
from llm_manager.infrastructure import root_restore_review_cli as cli
from tests.test_root_restore_review_client import Runner, wire
from tests.test_local_root_restore_protocol import NOW, request
from tests import test_root_restore_store as fixture


class RootRestoreStatusClientTests(unittest.TestCase):
    def setUp(self):
        self.request = request()
        self.attempt = RootRestoreAttempt(self.request.request_id, self.request.request_hash, 'a'*64, NOW)
        self.result = RootRestoreResult(self.request.request_id, self.request.request_hash,
            _digest('attempt', self.attempt), RootRestoreState.COMMITTED, NOW, None)
        self.value = dict(status='execution_status', request_id=self.request.request_id,
            request_hash=self.request.request_hash, state='committed', requires_attention=False,
            attempt=to_primitive(self.attempt), result=to_primitive(self.result))
        self.runner = Runner(self.value)
        self.client = RootRestoreReviewClient(caller_uid=1000, host_id=self.request.host_id,
            runner=self.runner, clock=lambda: NOW + timedelta(days=1))
        self.token = CancellationToken()

    def read(self, value=None):
        if value is not None:
            self.runner.result = replace(self.runner.result, stdout=wire(value))
        return self.client.status(self.request, self.token)

    def test_expired_intent_uses_exact_status_command_and_decodes_history(self):
        self.assertEqual(self.read().result, self.result)
        command = self.runner.calls[0]
        self.assertEqual(command.argv, ('/usr/bin/pkexec', REVIEW_HELPER, 'status', self.request.request_id, self.request.request_hash))
        self.assertEqual(command.timeout_ms, 120000)

    def test_review_only_attempt_only_failed_unknown_states(self):
        for state in ('review_only', 'unknown', 'failed'):
            value = deepcopy(self.value)
            value['state'] = state
            value['requires_attention'] = state != 'review_only'
            if state == 'review_only':
                value['attempt'] = value['result'] = None
            elif state == 'unknown':
                value['result'] = None
            else:
                value['result']['state'] = 'failed'
                value['result']['error_code'] = 'validation_failed'
            self.assertEqual(self.read(value).requires_attention, state != 'review_only')

    def test_binding_schema_type_and_time_forgery_are_rejected(self):
        changes = [('request_hash', 'f'*64), ('request_id', 'other'), ('state', 'review_only'),
                   ('requires_attention', 0), ('extra', True), ('attempt', None)]
        for key, value in changes:
            invalid = deepcopy(self.value); invalid[key] = value
            with self.subTest(key=key), self.assertRaises(AdapterError): self.read(invalid)
        for section, key, value in (('attempt', 'request_hash', 'f'*64),
                ('attempt', 'review_hash', 'bad'), ('attempt', 'started_at', '2020-01-01T00:00:00+00:00'),
                ('attempt', 'started_at', '2026-09-05T00:00:00'),
                ('result', 'attempt_hash', 'f'*64), ('result', 'error_code', 'secret text'),
                ('result', 'completed_at', '2020-01-01T00:00:00+00:00')):
            invalid = deepcopy(self.value); invalid[section][key] = value
            with self.subTest(section=section, key=key), self.assertRaises(AdapterError): self.read(invalid)

    def test_invalid_identity_and_cancel_do_not_launch(self):
        self.client.caller_uid = 1001
        with self.assertRaises(AdapterError): self.read()
        self.client.caller_uid = 1000
        self.token.cancel()
        with self.assertRaises(OperationCancelled): self.read()
        self.assertEqual(self.runner.calls, [])

    def test_malformed_oversized_failure_and_timeout_are_one_shot(self):
        for output, code, timeout in (('[]\n', 0, False), ('x'*32769, 0, False),
            (wire(self.value)+'\n', 0, False), (wire(self.value), 0, True),
            (wire({'status':'failed', 'error_code':'secret-sentinel'}), 1, False),
            ('', 126, False)):
            self.runner.calls.clear()
            self.runner.result = replace(self.runner.result, stdout=output, exit_code=code, timed_out=timeout)
            with self.assertRaises(AdapterError) as error: self.read()
            self.assertNotIn('secret-sentinel', str(error.exception))
            self.assertEqual(len(self.runner.calls), 1)

    def test_late_cancel_discards_success(self):
        run = self.runner.run
        def cancelled(command, token):
            result = run(command, token); token.cancel(); return result
        self.runner.run = cancelled
        with self.assertRaises(OperationCancelled): self.read()
        self.assertEqual(len(self.runner.calls), 1)


class RootRestoreStatusClientIntegrationTests(unittest.TestCase):
    setUp = fixture.RootRestoreStoreTests.setUp
    begin = fixture.RootRestoreStoreTests.begin

    def test_client_real_cli_and_store_history_without_mutation(self):
        attempt = self.begin()
        saved = self.store.finish(attempt, RootRestoreState.UNKNOWN, 'validation_failed', self.token)
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        self.now = NOW + timedelta(days=1)
        @contextmanager
        def factory(): yield self.store
        class CliRunner:
            def run(inner, command, cancellation):
                output = io.StringIO()
                with patch.object(cli, 'production_status', factory), patch.object(cli, 'resolve_restore_caller', return_value=RestoreCaller(1000, self.request.host_id)), redirect_stdout(output):
                    code = cli.main(list(command.argv[2:]))
                return CommandResult((), code, output.getvalue(), '', False, 1)
        client = RootRestoreReviewClient(caller_uid=1000, host_id=self.request.host_id, runner=CliRunner())
        self.assertEqual(client.status(self.request, self.token).result, saved)
        self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir()}, before)
        with self.assertRaises(AdapterError): self.begin()
