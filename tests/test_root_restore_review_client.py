import io
import json
import unittest
from contextlib import contextmanager, redirect_stdout
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandResult
from llm_manager.domain.serialization import to_primitive
from llm_manager.infrastructure.root_restore_review import RootRestoreSelection, RestoreCaller
from llm_manager.infrastructure.root_backup_evidence import RootBackupInventoryItem
from llm_manager.infrastructure.root_restore_review_client import RootRestoreReviewClient, REVIEW_HELPER
from llm_manager.infrastructure import root_restore_review_cli as cli
from llm_manager.infrastructure.local_root_restore_protocol import decode_request
from tests.test_local_root_restore_protocol import NOW, request
from tests import test_root_restore_review as review_fixture


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n'


class Runner:
    def __init__(self, value):
        self.result = CommandResult((), 0, wire(value), '', False, 1)
        self.calls = []

    def run(self, command, cancellation):
        self.calls.append(command)
        return self.result


class RootRestoreReviewClientTests(unittest.TestCase):
    def setUp(self):
        r = request()
        self.selection = RootRestoreSelection(r.host_id, r.caller_uid, r.backup_id,
            r.manifest_hash, 'f'*64, 'a'*64, r.inventory_hash, r.target, r.current, r.backup,
            r.requested_at, r.expires_at)
        self.value = {'status': 'preview', 'selection': to_primitive(self.selection),
                      'preview_hash': self.selection.preview_hash}
        self.runner = Runner(self.value)
        self.client = RootRestoreReviewClient(caller_uid=1000, host_id=r.host_id,
            runner=self.runner, clock=lambda: NOW)
        self.token = CancellationToken()

    def test_preview_validates_and_uses_only_dedicated_entry(self):
        self.assertEqual(self.client.preview('backup-1', self.token), self.selection)
        cmd = self.runner.calls[0]
        self.assertEqual(cmd.argv, ('/usr/bin/pkexec', REVIEW_HELPER, 'preview', 'backup-1'))
        self.assertEqual(cmd.timeout_ms, 120000)

    def test_inventory_validates_bounded_sorted_items_and_uses_review_entry(self):
        item = RootBackupInventoryItem(
            'backup-1', self.selection.host_id, NOW, self.selection.backup,
            'f' * 64, 'a' * 64, 'b' * 64,
        )
        self.runner.result = replace(self.runner.result, stdout=wire({
            'status': 'root_backup_inventory', 'host_id': self.selection.host_id,
            'items': [to_primitive(item)],
        }))
        self.assertEqual(self.client.list_backups(self.token), (item,))
        self.assertEqual(self.runner.calls[0].argv,
                         ('/usr/bin/pkexec', REVIEW_HELPER, 'list'))

    def test_inventory_rejects_wrong_host_order_duplicates_and_forged_metadata(self):
        first = RootBackupInventoryItem('b', self.selection.host_id, NOW,
            self.selection.backup, 'f'*64, 'a'*64, 'b'*64)
        second = replace(first, backup_id='a')
        cases = (
            {'status': 'root_backup_inventory', 'host_id': 'other', 'items': []},
            {'status': 'root_backup_inventory', 'host_id': self.selection.host_id,
             'items': [to_primitive(first), to_primitive(second)]},
            {'status': 'root_backup_inventory', 'host_id': self.selection.host_id,
             'items': [to_primitive(first), to_primitive(first)]},
            {'status': 'root_backup_inventory', 'host_id': self.selection.host_id,
             'items': [{**to_primitive(first), 'record_hash': 'bad'}]},
        )
        for value in cases:
            self.runner.result = replace(self.runner.result, stdout=wire(value))
            with self.subTest(value=value), self.assertRaises(AdapterError):
                self.client.list_backups(self.token)

    def test_approve_binds_exact_preview_and_checks_receipt(self):
        intent = self.selection.request('restore-1', 'approval-1')
        self.runner.result = replace(self.runner.result, stdout=wire({'status': 'review_saved',
            'request_id': intent.request_id, 'request_hash': intent.request_hash}))
        saved = self.client.approve(self.selection, request_id='restore-1', approval_id='approval-1', cancellation=self.token)
        self.assertEqual(saved.request_hash, intent.request_hash)
        argv = self.runner.calls[0].argv
        self.assertEqual(argv[:3], ('/usr/bin/pkexec', REVIEW_HELPER, 'approve'))
        self.assertEqual(decode_request(bytes.fromhex(argv[4]), expected_hash=argv[3],
            expected_caller_uid=1000, expected_host_id=intent.host_id, now=NOW), intent)

    def test_unrelated_receipt_is_not_success(self):
        with self.assertRaises(AdapterError):
            self.client.approve(self.selection, request_id='restore-1', approval_id='approval-1', cancellation=self.token)
        self.assertEqual(len(self.runner.calls), 1)

    def test_preview_rejects_malformed_and_noncanonical_output(self):
        for output in ('[]\n', '{}\n', '{"status":"preview","status":"preview"}\n',
                       wire(self.value)+'\n', 'x'*32769, '{"x":NaN}\n', '['*1500):
            with self.subTest(output=output[:50]):
                self.runner.result = replace(self.runner.result, stdout=output)
                with self.assertRaises(AdapterError): self.client.preview('backup-1', self.token)

    def test_rehashed_preview_still_requires_identity_target_metadata_and_expiry(self):
        for change in ({'caller_uid': True}, {'caller_uid': 1001}, {'host_id': 'other'},
                       {'backup_id': 'other'}, {'target': '/tmp/arbitrary'},
                       {'expires_at': NOW}, {'origin_record_hash': 'invalid'},
                       {'created_at': NOW + timedelta(seconds=1)}):
            selection = replace(self.selection, **change)
            self.runner.result = replace(self.runner.result, stdout=wire({'status': 'preview',
                'selection': to_primitive(selection), 'preview_hash': selection.preview_hash}))
            with self.subTest(change=change), self.assertRaises(AdapterError):
                self.client.preview('backup-1', self.token)

    def test_invalid_input_expiry_cancel_never_launch(self):
        with self.assertRaises(AdapterError): self.client.preview('../backup', self.token)
        self.client.clock = lambda: NOW + timedelta(minutes=5)
        with self.assertRaises(AdapterError):
            self.client.approve(self.selection, request_id='r', approval_id='a', cancellation=self.token)
        with self.assertRaises(OperationCancelled):
            self.client.preview('backup-1', CancellationToken(cancelled=True))
        self.assertEqual(self.runner.calls, [])

    def test_failure_timeout_and_denial_are_one_shot_and_redacted(self):
        for code, timeout, expected in ((126, False, 'privilege_denied'),
                (127, False, 'restore_review_launch_failed'), (None, True, 'restore_review_timeout'),
                (1, False, 'restore_review_rejected'), (9, False, 'restore_review_unavailable')):
            self.runner.calls.clear()
            self.runner.result = replace(self.runner.result, exit_code=code, timed_out=timeout,
                stdout=wire({'status': 'failed', 'error_code': 'secret-sentinel'}), stderr_redacted='secret-sentinel')
            with self.assertRaises(AdapterError) as error: self.client.preview('backup-1', self.token)
            self.assertEqual(error.exception.code, expected)
            self.assertNotIn('secret-sentinel', str(error.exception))
            self.assertEqual(len(self.runner.calls), 1)

    def test_late_cancel_discards_success_without_retry(self):
        original = self.runner.run
        def run(command, token):
            result = original(command, token)
            token.cancel()
            return result
        self.runner.run = run
        with self.assertRaises(OperationCancelled): self.client.preview('backup-1', self.token)
        self.assertEqual(len(self.runner.calls), 1)


class RootRestoreReviewClientIntegrationTests(unittest.TestCase):
    setUp = review_fixture.RootRestoreReviewTests.setUp
    run_capture = review_fixture.RootRestoreReviewTests.run_capture
    prepare = review_fixture.RootRestoreReviewTests.prepare
    make = review_fixture.RootRestoreReviewTests.make

    def test_real_cli_preview_approve_persists_review_without_target_mutation(self):
        self.make()
        @contextmanager
        def production(caller):
            yield self.producer
        class CliRunner:
            def run(inner, command, cancellation):
                output = io.StringIO()
                with patch.object(cli, 'resolve_restore_caller', self.producer.identity), \
                     patch.object(cli, 'production_review', production), redirect_stdout(output):
                    code = cli.main(list(command.argv[2:]))
                return CommandResult((), code, output.getvalue(), '', False, 1)
        client = RootRestoreReviewClient(caller_uid=1000, host_id=self.record.host_id,
                                        runner=CliRunner(), clock=lambda: NOW)
        selection = client.preview('backup-1', self.token)
        receipt = client.approve(selection, request_id='client-review', approval_id='consent-1', cancellation=self.token)
        saved = self.store.load_review(receipt.request_id, self.token)
        self.assertEqual(saved.approved_request, selection.request('client-review', 'consent-1'))
        self.assertEqual(self.target.read_bytes(), b'new current settings')
        self.assertTrue(self.store.request_is_unused(receipt.request_id, self.token))

    def test_client_real_cli_lists_root_origin_without_keys_or_target(self):
        import os
        from llm_manager.infrastructure.root_backup_evidence import RootBackupEvidenceReader
        self.make()
        outer = self
        class CliRunner:
            def run(inner, command, cancellation):
                output = io.StringIO()
                def opener():
                    return os.open(outer.root / 'store', os.O_RDONLY | os.O_DIRECTORY)
                with patch.object(cli, 'resolve_restore_caller', return_value=RestoreCaller(
                        1000, outer.record.host_id)), \
                     patch.object(cli, 'open_production_directory', side_effect=opener), \
                     patch.object(cli, 'RootBackupEvidenceReader', side_effect=lambda fd:
                         RootBackupEvidenceReader(fd, owner_uid=os.getuid(), owner_gid=os.getgid())), \
                     redirect_stdout(output):
                    code = cli.main(list(command.argv[2:]))
                return CommandResult((), code, output.getvalue(), '', False, 1)
        client = RootRestoreReviewClient(caller_uid=1000, host_id=self.record.host_id,
                                         runner=CliRunner(), clock=lambda: NOW)
        items = client.list_backups(CancellationToken())
        self.assertEqual([item.backup_id for item in items], ['backup-1'])
        self.assertEqual(items[0].record_hash, self.record.record_hash)
