import os
import unittest
from unittest.mock import patch

from llm_manager.application.errors import AdapterError
from llm_manager.application.host_discovery import HostCandidate
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.enums import HostKind
from llm_manager.infrastructure.root_backup_evidence import RootBackupInventoryItem
from llm_manager.infrastructure.root_restore_review import RootRestoreSelection
from llm_manager.infrastructure.root_restore_review_client import SavedRootRestoreReview
from llm_manager.ui.root_restore_inventory import (
    RootRestoreInventorySession, production_inventory_session,
)
from llm_manager.ui.root_restore_review import RootRestoreReviewSession
from tests.test_local_root_restore_protocol import NOW, request


class ReviewClient:
    caller_uid = 1000
    host_id = 'local:host'
    def __init__(self, items, selection):
        self.items, self.selection, self.calls = items, selection, []
    def list_backups(self, token): self.calls.append('list'); return self.items
    def preview(self, backup_id, token): self.calls.append(('preview', backup_id)); return self.selection
    def validate_selection(self, selection): return None
    def approve(self, selection, *, request_id, approval_id, cancellation):
        intent = selection.request(request_id, approval_id)
        self.calls.append(('approve', request_id))
        return SavedRootRestoreReview(request_id, intent.request_hash)
    def status(self, request, token): raise AssertionError('status not expected')


class ExecuteClient:
    caller_uid = 1000
    host_id = 'local:host'


class RootRestoreInventorySessionTests(unittest.TestCase):
    def setUp(self):
        intent = request()
        self.selection = RootRestoreSelection(
            intent.host_id, intent.caller_uid, intent.backup_id, intent.manifest_hash,
            'f'*64, 'a'*64, intent.inventory_hash, intent.target, intent.current,
            intent.backup, intent.requested_at, intent.expires_at,
        )
        self.item = RootBackupInventoryItem(
            intent.backup_id, intent.host_id, NOW, intent.backup,
            'f'*64, 'a'*64, intent.manifest_hash,
        )
        self.review = ReviewClient((self.item,), self.selection)
        self.session = RootRestoreInventorySession(self.review, ExecuteClient())
        self.token = CancellationToken()

    def load(self):
        task = self.session.list_task()
        self.session.receive_inventory(task(self.token))

    def test_load_select_review_save_and_exact_execution_handoff(self):
        self.load()
        self.assertEqual(self.session.state, 'ready')
        self.assertFalse(self.session.can_review)
        self.session.select('backup-1')
        review = self.session.create_review_session()
        review.clock = lambda: NOW
        review.receive_preview(review.preview_task()(self.token))
        review.consent(True)
        receipt = review.save_task()(self.token)
        review.receive_receipt(receipt)
        execution = self.session.create_execution_session(review)
        self.assertEqual(execution.request.request_hash, receipt.request_hash)
        self.assertFalse(execution.can_execute)
        self.assertEqual(self.review.calls[0], 'list')

    def test_inventory_is_one_shot_and_empty_failure_or_invalid_results_do_not_select(self):
        self.load()
        with self.assertRaises(AdapterError): self.session.list_task()
        self.session.select('other')
        self.assertFalse(self.session.can_review)
        for items, state in (((), 'empty'), ((object(),), 'failed')):
            session = RootRestoreInventorySession(ReviewClient(items, self.selection), ExecuteClient())
            task = session.list_task()
            if state == 'failed':
                with self.assertRaises(AdapterError): session.receive_inventory(task(self.token))
            else: session.receive_inventory(task(self.token))
            self.assertEqual(session.state, state)
            self.assertFalse(session.can_review)

    def test_rejects_unsorted_duplicate_wrong_host_and_unrelated_review(self):
        cases = (
            (self.item, self.item),
            (RootBackupInventoryItem('z', self.item.host_id, NOW, self.item.original,
                                     'f'*64, 'a'*64, 'b'*64), self.item),
            (RootBackupInventoryItem(self.item.backup_id, 'other', NOW, self.item.original,
                                     'f'*64, 'a'*64, 'b'*64),),
        )
        for items in cases:
            session = RootRestoreInventorySession(ReviewClient(items, self.selection), ExecuteClient())
            session.list_task()
            with self.subTest(items=items), self.assertRaises(AdapterError):
                session.receive_inventory(items)
        self.load(); self.session.select('backup-1')
        with self.assertRaises(AdapterError):
            self.session.create_execution_session(RootRestoreReviewSession(
                ReviewClient((self.item,), self.selection), 'backup-1'))

    def test_identity_mismatch_and_production_remote_wrong_host_root_fail_before_clients(self):
        execute = ExecuteClient(); execute.host_id = 'local:other'
        with self.assertRaises(AdapterError): RootRestoreInventorySession(self.review, execute)
        local_id = 'local:' + os.uname().nodename
        hosts = (HostCandidate('ssh:x', HostKind.SSH, 'x'),
                 HostCandidate('local:wrong', HostKind.LOCAL, 'wrong'))
        with patch('llm_manager.ui.root_restore_inventory.os.getuid', return_value=1000), \
             patch('llm_manager.ui.root_restore_inventory.RootRestoreReviewClient') as client:
            for host in hosts:
                with self.assertRaises(AdapterError): production_inventory_session(host)
            client.assert_not_called()
        with patch('llm_manager.ui.root_restore_inventory.os.getuid', return_value=0), \
             patch('llm_manager.ui.root_restore_inventory.RootRestoreReviewClient') as client:
            with self.assertRaises(AdapterError): production_inventory_session(
                HostCandidate(local_id, HostKind.LOCAL, 'local'))
            client.assert_not_called()


if __name__ == '__main__': unittest.main()
