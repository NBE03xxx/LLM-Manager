import io
import json
import os
import unittest
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch, Mock
import xml.etree.ElementTree as ET

from llm_manager.infrastructure import root_restore_review_cli as cli
from llm_manager.infrastructure.local_root_restore_protocol import encode_request
from llm_manager.infrastructure.root_restore_review import RestoreCaller
from llm_manager.infrastructure.root_backup_evidence import RootBackupEvidenceReader
from tests import test_root_restore_review as fixture


class RootRestoreReviewCliTests(unittest.TestCase):
    setUp = fixture.RootRestoreReviewTests.setUp
    run_capture = fixture.RootRestoreReviewTests.run_capture
    prepare = fixture.RootRestoreReviewTests.prepare
    make = fixture.RootRestoreReviewTests.make

    def invoke(self, args):
        @contextmanager
        def factory(caller):
            self.assertEqual(caller.uid, 1000)
            yield self.producer
        output = io.StringIO()
        with patch.object(cli, 'resolve_restore_caller', return_value=RestoreCaller(1000, self.record.host_id)), patch.object(cli, 'production_review', factory), redirect_stdout(output):
            code = cli.main(args)
        return code, json.loads(output.getvalue())

    def test_cli_preview_and_approve_with_real_store(self):
        intent = self.make()
        code, result = self.invoke(['preview', 'backup-1'])
        self.assertEqual(code, 0)
        self.assertEqual(result['preview_hash'], self.selection.preview_hash)
        code, result = self.invoke(['approve', intent.request_hash, encode_request(intent).hex()])
        self.assertEqual(code, 0)
        self.assertEqual(result, {'status': 'review_saved', 'request_id': intent.request_id, 'request_hash': intent.request_hash})
        self.assertEqual(self.store.load_review(intent.request_id, self.token).approved_request, intent)
        self.assertEqual(self.target.read_bytes(), b'new current settings')

    def test_cli_lists_only_current_host_without_opening_key_target_or_execution_store(self):
        self.make()
        output = io.StringIO()
        def opener():
            return os.open(self.root / 'store', os.O_RDONLY | os.O_DIRECTORY)
        with patch.object(cli, 'resolve_restore_caller', return_value=RestoreCaller(1000, self.record.host_id)), \
             patch.object(cli, 'open_production_directory', side_effect=opener), \
             patch.object(cli, 'RootBackupEvidenceReader', side_effect=lambda fd: RootBackupEvidenceReader(
                 fd, owner_uid=os.getuid(), owner_gid=os.getgid())), \
             patch.object(cli, 'production_review') as review, \
             patch.object(cli, 'production_status') as status, redirect_stdout(output):
            self.assertEqual(cli.main(['list']), 0)
        review.assert_not_called(); status.assert_not_called()
        value = json.loads(output.getvalue())
        self.assertEqual(value['status'], 'root_backup_inventory')
        self.assertEqual([item['backup_id'] for item in value['items']], ['backup-1'])
        self.assertNotIn('key_id', value['items'][0])

    def test_invalid_transport_rejected_before_opening_root_paths(self):
        cases = [['preview', '../backup'], ['approve', 'a'*64, ''],
                 ['approve', 'a'*64, 'gg'], ['approve', 'a'*64, 'AA'],
                 ['approve', 'a'*64, 'aa aa'], ['approve', 'a'*64, 'a'],
                 ['approve', 'a'*64, '00'*(cli.MAX_REQUEST_BYTES+1)],
                 ['approve', 'bad', '00']]
        for args in cases:
            with self.subTest(args=args[:2]), patch.object(cli, 'resolve_restore_caller', return_value=RestoreCaller(1000, 'local:test')), patch.object(cli, 'production_review') as factory, redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(args), 1)
                factory.assert_not_called()

    def test_nonroot_fails_before_store_access(self):
        with patch('os.geteuid', return_value=1000), patch.object(cli, 'production_review') as factory, redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['preview', 'backup-1']), 1)
            factory.assert_not_called()

    def test_unexpected_failure_is_redacted(self):
        output = io.StringIO()
        with patch.object(cli, 'resolve_restore_caller', side_effect=RuntimeError('SECRET CONFIG')), redirect_stdout(output):
            self.assertEqual(cli.main(['preview', 'backup-1']), 1)
        self.assertNotIn('SECRET', output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['error_code'], 'restore_review_unavailable')

    def test_no_mutation_or_arbitrary_path_subcommand(self):
        for args in (['execute', 'backup-1'], ['preview', 'backup-1', '--path', '/tmp/test']):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                cli.main(args)
            self.assertEqual(caught.exception.code, 2)

    def test_composition_closes_open_fds_on_partial_failure(self):
        with patch.object(cli, 'open_production_directory', return_value=101), patch.object(cli, 'open_production_key_directory', side_effect=OSError('unavailable')), patch.object(cli.os, 'close') as close:
            with self.assertRaises(OSError):
                with cli.production_review(RestoreCaller(1000, 'local:test')): pass
            close.assert_called_once_with(101)

    def test_composition_uses_fixed_openers_and_closes_all_fds(self):
        with patch.object(cli, 'open_production_directory', return_value=101), patch.object(cli, 'open_production_key_directory', return_value=102), patch.object(cli, 'open_production_source_parent', return_value=103), patch.object(cli, 'open_production_execution_directory', return_value=104), patch.object(cli.os, 'close') as close:
            with cli.production_review(RestoreCaller(1000, 'local:test')) as producer:
                self.assertEqual(producer.identity(), RestoreCaller(1000, 'local:test'))
                self.assertEqual(producer.origins.owner_uid, 0)
            self.assertEqual([c.args[0] for c in close.call_args_list], [104, 103, 102, 101])

    def test_review_policy_is_separate_and_does_not_cache_auth(self):
        root = Path(__file__).resolve().parents[1]
        policy = ET.parse(root / 'packaging/polkit/io.github.nbe03xxx.llm-manager.policy')
        actions = {a.attrib['id']: a for a in policy.findall('action')}
        review = actions['io.github.nbe03xxx.llm-manager.review-system-restore']
        self.assertEqual(review.findtext('defaults/allow_active'), 'auth_admin')
        self.assertEqual(review.findtext('defaults/allow_any'), 'no')
        self.assertEqual(review.findtext('defaults/allow_inactive'), 'no')
        self.assertEqual(review.findtext('annotate'), '/usr/bin/llm-manager-restore-review')
        self.assertEqual(actions['io.github.nbe03xxx.llm-manager.apply-system-settings'].findtext('annotate'), '/usr/bin/llm-manager-helper')
        launcher = root / 'packaging/bin/llm-manager-restore-review'
        self.assertTrue(launcher.read_text().startswith('#!/usr/bin/python3 -I\n'))
        self.assertIn('packaging/bin/llm-manager-restore-review usr/bin', (root / 'debian/llm-manager.install').read_text())
