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
from llm_manager.infrastructure import root_restore_execute_cli as cli
from llm_manager.infrastructure.local_root_restore_protocol import encode_request
from llm_manager.infrastructure.root_restore_execute_client import (
    EXECUTE_HELPER, RootRestoreExecuteClient, RootRestoreExecutionUnconfirmed,
)
from llm_manager.infrastructure.root_restore_review import RestoreCaller
from llm_manager.infrastructure.root_restore_store import RootRestoreResult, RootRestoreState
from tests import test_root_restore_execution as fixture
from tests.test_local_root_restore_protocol import NOW, request
from tests.test_root_restore_review_client import Runner, wire


class RootRestoreExecuteClientTests(unittest.TestCase):
    def setUp(self):
        self.request = request()
        self.record = RootRestoreResult(
            self.request.request_id, self.request.request_hash, 'a' * 64,
            RootRestoreState.COMMITTED, NOW, None,
        )
        self.value = {
            'status': 'execution_recorded', 'request_id': self.request.request_id,
            'request_hash': self.request.request_hash, 'state': 'committed',
            'requires_attention': False, 'result': to_primitive(self.record),
        }
        self.runner = Runner(self.value)
        self.client = RootRestoreExecuteClient(
            caller_uid=1000, host_id=self.request.host_id, runner=self.runner, clock=lambda: NOW,
        )
        self.token = CancellationToken()

    def execute(self, value=None):
        if value is not None:
            self.runner.result = replace(self.runner.result, stdout=wire(value))
        return self.client.execute(self.request, self.token)

    def test_exact_request_uses_only_dedicated_entry_and_decodes_committed_result(self):
        self.assertEqual(self.execute(), self.record)
        command = self.runner.calls[0]
        self.assertEqual(command.argv[:3], ('/usr/bin/pkexec', EXECUTE_HELPER, self.request.request_hash))
        self.assertEqual(bytes.fromhex(command.argv[3]), encode_request(self.request))
        self.assertEqual(command.timeout_ms, 180000)
        self.assertEqual(len(self.runner.calls), 1)

    def test_failed_and_unknown_recorded_results_are_returned_for_explicit_attention(self):
        for state, code in ((RootRestoreState.FAILED, 'service_validation_failed'),
                            (RootRestoreState.UNKNOWN, 'mutation_failed')):
            record = replace(self.record, state=state, error_code=code)
            value = {**self.value, 'state': state.value, 'requires_attention': True,
                     'result': to_primitive(record)}
            self.assertEqual(self.execute(value), record)

    def test_unconfirmed_timeout_cancel_runner_failure_and_any_bad_output_are_one_shot(self):
        cases = (
            replace(self.runner.result, timed_out=True, exit_code=None),
            replace(self.runner.result, exit_code=9),
            replace(self.runner.result, stdout='[]\n'),
            replace(self.runner.result, stdout='x' * 32769),
            replace(self.runner.result, stdout=wire(self.value) + '\n'),
        )
        for result in cases:
            self.runner.calls.clear(); self.runner.result = result
            with self.subTest(result=result), self.assertRaises(RootRestoreExecutionUnconfirmed):
                self.execute()
            self.assertEqual(len(self.runner.calls), 1)
        self.runner.calls.clear()
        original = self.runner.run
        def late_cancel(command, token):
            result = original(command, token); token.cancel(); return result
        self.runner.run = late_cancel
        with self.assertRaises(RootRestoreExecutionUnconfirmed): self.execute()
        self.assertEqual(len(self.runner.calls), 1)
        self.token = CancellationToken()
        self.runner.run = lambda command, token: (_ for _ in ()).throw(
            AdapterError('command_output_too_large', 'private-sentinel')
        )
        with self.assertRaises(RootRestoreExecutionUnconfirmed) as caught: self.execute()
        self.assertNotIn('private-sentinel', str(caught.exception))

    def test_canonical_failed_and_bound_unconfirmed_both_require_status(self):
        values = (
            {'status': 'failed', 'error_code': 'private-sentinel'},
            {'status': 'execution_unconfirmed', 'request_id': self.request.request_id,
             'request_hash': self.request.request_hash, 'state': 'unknown'},
        )
        for value in values:
            self.runner.result = replace(self.runner.result, exit_code=1, stdout=wire(value))
            with self.subTest(value=value), self.assertRaises(RootRestoreExecutionUnconfirmed) as caught:
                self.execute()
            self.assertNotIn('private-sentinel', str(caught.exception))
            self.assertEqual(caught.exception.request_id, self.request.request_id)
        self.assertEqual(caught.exception.reported_state, RootRestoreState.UNKNOWN)

    def test_unconfirmed_binding_forgery_is_not_exposed_as_authoritative(self):
        base = {'status': 'execution_unconfirmed', 'request_id': self.request.request_id,
                'request_hash': self.request.request_hash, 'state': 'unknown'}
        for key, value in (('request_id', 'other'), ('request_hash', 'f' * 64),
                           ('state', 'review_only'), ('extra', True)):
            forged = dict(base); forged[key] = value
            self.runner.result = replace(self.runner.result, exit_code=1, stdout=wire(forged))
            with self.subTest(key=key), self.assertRaises(RootRestoreExecutionUnconfirmed) as caught:
                self.execute()
            self.assertIsNone(caught.exception.reported_state)

    def test_record_binding_schema_state_time_and_summary_forgery_are_unconfirmed(self):
        cases = []
        for key, value in (('request_id', 'other'), ('request_hash', 'f' * 64),
                           ('state', 'failed'), ('requires_attention', True), ('extra', True)):
            forged = deepcopy(self.value); forged[key] = value; cases.append(forged)
        for key, value in (('request_id', 'other'), ('request_hash', 'f' * 64),
                           ('attempt_hash', 'bad'), ('completed_at', '2026-09-05T10:00:00'),
                           ('error_code', 'failure')):
            forged = deepcopy(self.value); forged['result'][key] = value; cases.append(forged)
        for forged in cases:
            with self.subTest(forged=forged), self.assertRaises(RootRestoreExecutionUnconfirmed):
                self.execute(forged)

    def test_denial_and_launch_failure_are_known_preexecution_outcomes(self):
        for code, expected in ((126, 'privilege_denied'), (127, 'root_restore_launch_failed')):
            self.runner.calls.clear()
            self.runner.result = replace(self.runner.result, exit_code=code, stdout='')
            with self.assertRaises(AdapterError) as caught: self.execute()
            self.assertNotIsInstance(caught.exception, RootRestoreExecutionUnconfirmed)
            self.assertEqual(caught.exception.code, expected)
            self.assertEqual(len(self.runner.calls), 1)

    def test_timeout_or_late_cancel_takes_precedence_over_authentication_exit_codes(self):
        for code in (126, 127):
            for timed_out in (False, True):
                with self.subTest(code=code, timed_out=timed_out):
                    self.setUp()
                    self.runner.result = replace(
                        self.runner.result, exit_code=code, timed_out=timed_out, stdout='',
                    )
                    original = self.runner.run
                    def run(command, token):
                        result = original(command, token)
                        if not timed_out:
                            token.cancel()
                        return result
                    self.runner.run = run
                    with self.assertRaises(RootRestoreExecutionUnconfirmed):
                        self.execute()
                    self.assertEqual(len(self.runner.calls), 1)

    def test_invalid_identity_expiry_and_precancel_never_launch(self):
        self.client.caller_uid = 1001
        with self.assertRaises(AdapterError): self.execute()
        self.client.caller_uid = 1000
        self.client.clock = lambda: NOW + timedelta(minutes=5)
        with self.assertRaises(AdapterError): self.execute()
        self.client.clock = lambda: NOW
        self.token.cancel()
        with self.assertRaises(OperationCancelled): self.execute()
        self.assertEqual(self.runner.calls, [])


class RootRestoreExecuteClientIntegrationTests(unittest.TestCase):
    setUp = fixture.RootRestoreExecutionTests.setUp
    run_capture = fixture.RootRestoreExecutionTests.run_capture
    prepare = fixture.RootRestoreExecutionTests.prepare
    make = fixture.RootRestoreExecutionTests.make

    def test_client_real_cli_and_coordinator_mutate_once(self):
        self.make()
        intent = self.review.approved_request
        @contextmanager
        def production(): yield self.coordinator
        class CliRunner:
            def run(inner, command, cancellation):
                output = io.StringIO()
                with patch.object(cli, 'resolve_restore_caller', return_value=RestoreCaller(1000, intent.host_id)), \
                     patch.object(cli, 'production_execution', production), \
                     patch.object(cli, 'utc_now', return_value=NOW), redirect_stdout(output):
                    code = cli.main(list(command.argv[2:]))
                return CommandResult((), code, output.getvalue(), '', False, 1)
        client = RootRestoreExecuteClient(
            caller_uid=1000, host_id=intent.host_id, runner=CliRunner(), clock=lambda: NOW,
        )
        result = client.execute(intent, self.token)
        self.assertEqual(result.state, RootRestoreState.COMMITTED)
        self.assertEqual(self.target.read_bytes(), self.original)
        with self.assertRaises(RootRestoreExecutionUnconfirmed): client.execute(intent, self.token)
        self.assertEqual(self.target.read_bytes(), self.original)
