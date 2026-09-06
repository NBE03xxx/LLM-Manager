import io
import json
import os
import stat
import unittest
import xml.etree.ElementTree as ET
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from llm_manager.application.errors import AdapterError
from llm_manager.domain.serialization import to_primitive
from llm_manager.infrastructure import root_restore_execute_cli as cli
from llm_manager.infrastructure.local_root_restore_protocol import encode_request
from llm_manager.infrastructure.root_restore_execution import RootRestorePersistenceError
from llm_manager.infrastructure.root_restore_review import RestoreCaller
from llm_manager.infrastructure.root_restore_store import RootRestoreResult, RootRestoreState
from tests import test_root_restore_execution as fixture
from tests.test_local_root_restore_protocol import NOW, request


class RootRestoreExecuteCliTests(unittest.TestCase):
    def setUp(self):
        self.request = request()
        self.record = RootRestoreResult(
            self.request.request_id, self.request.request_hash, 'f' * 64,
            RootRestoreState.COMMITTED, NOW, None,
        )
        self.executor = Mock()
        self.executor.execute.return_value = self.record

    def invoke(self, *, executor=None, caller=None, args=None):
        @contextmanager
        def production():
            yield executor or self.executor
        output = io.StringIO()
        with patch.object(cli, 'resolve_restore_caller', return_value=caller or RestoreCaller(1000, self.request.host_id)), \
             patch.object(cli, 'production_execution', production), \
             patch.object(cli, 'utc_now', return_value=NOW), redirect_stdout(output):
            code = cli.main(args or [self.request.request_hash, encode_request(self.request).hex()])
        return code, json.loads(output.getvalue())

    def test_exact_request_is_executed_once_and_committed_record_returned(self):
        code, value = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(value, {
            'status': 'execution_recorded', 'request_id': self.request.request_id,
            'request_hash': self.request.request_hash, 'state': 'committed',
            'requires_attention': False, 'result': to_primitive(self.record),
        })
        call = self.executor.execute.call_args
        self.assertEqual(call.args[0], self.request)
        self.assertEqual(call.kwargs['expected_hash'], self.request.request_hash)
        self.assertEqual(call.kwargs['caller_uid'], 1000)
        self.assertEqual(call.kwargs['host_id'], self.request.host_id)
        self.assertEqual(self.executor.execute.call_count, 1)

    def test_failed_and_unknown_terminal_records_are_successful_transport_with_attention(self):
        for state, error_code in ((RootRestoreState.FAILED, 'service_validation_failed'),
                                  (RootRestoreState.UNKNOWN, 'mutation_failed')):
            record = RootRestoreResult(
                self.request.request_id, self.request.request_hash, 'f' * 64,
                state, NOW, error_code,
            )
            self.executor.execute.return_value = record
            code, value = self.invoke()
            self.assertEqual(code, 0)
            self.assertEqual(value['state'], state.value)
            self.assertTrue(value['requires_attention'])

    def test_result_persistence_failure_is_unconfirmed_and_never_retried(self):
        self.executor.execute.side_effect = RootRestorePersistenceError(
            self.request.request_hash, RootRestoreState.UNKNOWN,
        )
        code, value = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(value, {
            'status': 'execution_unconfirmed', 'request_id': self.request.request_id,
            'request_hash': self.request.request_hash, 'state': 'unknown',
        })
        self.assertEqual(self.executor.execute.call_count, 1)

    def test_unbound_or_invalid_terminal_record_is_never_reported_as_success(self):
        from dataclasses import replace
        cases = (
            replace(self.record, request_id='other'),
            replace(self.record, request_hash='e' * 64),
            replace(self.record, attempt_hash='bad'),
            replace(self.record, state=RootRestoreState.COMMITTED, error_code='failure'),
            replace(self.record, state=RootRestoreState.UNKNOWN, error_code=None),
            replace(self.record, completed_at=NOW.replace(tzinfo=None)),
            object(),
        )
        for record in cases:
            with self.subTest(record=record):
                self.executor.reset_mock()
                self.executor.execute.return_value = record
                code, value = self.invoke()
                self.assertEqual(code, 1)
                self.assertEqual(value['status'], 'failed')
                self.assertEqual(self.executor.execute.call_count, 1)

    def test_invalid_transport_identity_expiry_and_hash_never_open_composition(self):
        cases = (
            ['', '00'], ['bad', '00'], ['a' * 64, ''], ['a' * 64, 'a'],
            ['a' * 64, 'gg'], ['a' * 64, 'AA'],
            ['a' * 64, '00' * (cli.MAX_REQUEST_BYTES + 1)],
            ['f' * 64, encode_request(self.request).hex()],
        )
        for args in cases:
            output = io.StringIO()
            with self.subTest(args=args[:1]), patch.object(
                cli, 'resolve_restore_caller', return_value=RestoreCaller(1000, self.request.host_id)
            ), patch.object(cli, 'production_execution') as production, patch.object(
                cli, 'utc_now', return_value=NOW
            ), redirect_stdout(output):
                self.assertEqual(cli.main(list(args)), 1)
                production.assert_not_called()
        with patch.object(cli, 'resolve_restore_caller', return_value=RestoreCaller(1001, self.request.host_id)), \
             patch.object(cli, 'production_execution') as production, redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main([self.request.request_hash, encode_request(self.request).hex()]), 1)
            production.assert_not_called()

    def test_unexpected_failure_is_redacted_and_cli_has_no_other_subcommand(self):
        self.executor.execute.side_effect = RuntimeError('PRIVATE SETTINGS SENTINEL')
        code, value = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(value, {'status': 'failed', 'error_code': 'root_restore_unavailable'})
        self.assertNotIn('PRIVATE', json.dumps(value))
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            cli.main(['status', self.request.request_hash, encode_request(self.request).hex()])
        self.assertEqual(caught.exception.code, 2)

    def test_execute_policy_launcher_and_package_are_dedicated(self):
        root = Path(__file__).resolve().parents[1]
        actions = {item.attrib['id']: item for item in ET.parse(
            root / 'packaging/polkit/io.github.nbe03xxx.llm-manager.policy'
        ).getroot().findall('action')}
        execute = actions['io.github.nbe03xxx.llm-manager.execute-system-restore']
        self.assertEqual(execute.findtext('defaults/allow_active'), 'auth_admin')
        self.assertEqual(execute.findtext('defaults/allow_any'), 'no')
        self.assertEqual(execute.findtext('defaults/allow_inactive'), 'no')
        self.assertEqual(execute.findtext('annotate'), '/usr/bin/llm-manager-restore-execute')
        self.assertEqual(actions['io.github.nbe03xxx.llm-manager.review-system-restore'].findtext('annotate'),
                         '/usr/bin/llm-manager-restore-review')
        launcher = root / 'packaging/bin/llm-manager-restore-execute'
        self.assertEqual(stat.S_IMODE(launcher.stat().st_mode), 0o755)
        self.assertTrue(launcher.read_text().startswith('#!/usr/bin/python3 -I\n'))
        self.assertIn('root_restore_execute_cli import main', launcher.read_text())
        self.assertIn('packaging/bin/llm-manager-restore-execute usr/bin',
                      (root / 'debian/llm-manager.install').read_text())
        self.assertIn('packaging/man/llm-manager-restore-execute.8',
                      (root / 'debian/llm-manager.manpages').read_text())


class RootRestoreExecuteCliIntegrationTests(unittest.TestCase):
    setUp = fixture.RootRestoreExecutionTests.setUp
    run_capture = fixture.RootRestoreExecutionTests.run_capture
    prepare = fixture.RootRestoreExecutionTests.prepare
    make = fixture.RootRestoreExecutionTests.make

    def test_real_coordinator_records_and_mutates_once(self):
        self.make()
        intent = self.review.approved_request
        @contextmanager
        def production():
            yield self.coordinator
        output = io.StringIO()
        with patch.object(cli, 'resolve_restore_caller', return_value=RestoreCaller(1000, intent.host_id)), \
             patch.object(cli, 'production_execution', production), \
             patch.object(cli, 'utc_now', return_value=NOW), redirect_stdout(output):
            code = cli.main([intent.request_hash, encode_request(intent).hex()])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['state'], 'committed')
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertFalse(self.store.request_is_unused(intent.request_id, self.token))
        with patch.object(cli, 'resolve_restore_caller', return_value=RestoreCaller(1000, intent.host_id)), \
             patch.object(cli, 'production_execution', production), \
             patch.object(cli, 'utc_now', return_value=NOW), redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main([intent.request_hash, encode_request(intent).hex()]), 1)
        self.assertEqual(self.target.read_bytes(), self.original)
