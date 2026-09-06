import unittest
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

from llm_manager.application.errors import AdapterError
from llm_manager.application.host_discovery import HostCandidate
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.enums import HostKind
from llm_manager.infrastructure.root_restore_review_client import SavedRootRestoreReview
from llm_manager.ui.root_restore_review import RootRestoreReviewSession, production_review_session
from tests import test_root_restore_review_client as fixture


class RootRestoreReviewSessionTests(unittest.TestCase):
    def setUp(self):
        f = fixture.RootRestoreReviewClientTests()
        f.setUp()
        self.client, self.selection = f.client, f.selection
        self.runner = f.runner
        self.session = RootRestoreReviewSession(self.client, 'backup-1', clock=lambda: fixture.NOW)
        self.token = CancellationToken()

    def ready(self):
        self.session.receive_preview(self.session.preview_task()(self.token))

    def test_explicit_consent_then_single_save_binds_receipt(self):
        self.ready()
        self.assertFalse(self.session.can_save)
        with self.assertRaises(AdapterError): self.session.save_task()
        self.session.consent(True)
        self.assertTrue(self.session.can_save)
        task = self.session.save_task()
        with self.assertRaises(AdapterError): self.session.save_task()
        request = self.session._request
        self.runner.result = replace(self.runner.result, stdout=fixture.wire({'status': 'review_saved',
            'request_id': request.request_id, 'request_hash': request.request_hash}))
        self.session.receive_receipt(task(self.token))
        self.assertEqual(self.session.state, 'saved')
        self.assertIsNone(self.session.selection)
        self.assertFalse(self.session.can_save)
        self.assertIs(self.session.approved_request_for_execution(), request)
        with self.assertRaises(AdapterError): self.session.preview_task()

    def test_execution_request_requires_saved_matching_live_receipt(self):
        with self.assertRaises(AdapterError): self.session.approved_request_for_execution()
        self.ready(); self.session.consent(True); task = self.session.save_task()
        request = self.session._request
        self.runner.result = replace(self.runner.result, stdout=fixture.wire({
            'status': 'review_saved', 'request_id': request.request_id,
            'request_hash': request.request_hash,
        }))
        self.session.receive_receipt(task(self.token))
        self.session.receipt = SavedRootRestoreReview('other', request.request_hash)
        with self.assertRaises(AdapterError): self.session.approved_request_for_execution()
        self.session.receipt = SavedRootRestoreReview(request.request_id, request.request_hash)
        self.session.clock = lambda: fixture.NOW + timedelta(minutes=5)
        with self.assertRaises(AdapterError): self.session.approved_request_for_execution()

    def test_unchecking_and_changed_selection_invalidate_consent(self):
        self.ready()
        self.session.consent(True)
        self.session.consent(False)
        self.assertFalse(self.session.can_save)
        self.session.consent(True)
        self.session.selection = replace(self.selection, inventory_hash='f'*64)
        self.assertFalse(self.session.can_save)

    def test_expiry_and_clock_regression_clear_selection_and_consent(self):
        for now in (fixture.NOW + timedelta(minutes=5), fixture.NOW - timedelta(seconds=1)):
            self.setUp()
            self.ready()
            self.session.consent(True)
            self.session.clock = lambda: now
            self.assertFalse(self.session.can_save)
            self.assertEqual(self.session.state, 'expired')
            self.assertIsNone(self.session.selection)
            with self.assertRaises(AdapterError): self.session.save_task()
            self.assertEqual(len(self.runner.calls), 1)

    def test_failed_or_cancelled_save_cannot_resend_or_accept_late_result(self):
        self.ready()
        self.session.consent(True)
        self.session.save_task()
        self.session.fail()
        with self.assertRaises(AdapterError): self.session.save_task()
        with self.assertRaises(AdapterError):
            self.session.receive_receipt(SavedRootRestoreReview('late', 'a'*64))
        self.assertIsNone(self.session.receipt)

    def test_other_receipt_and_other_backup_fail_closed(self):
        self.ready()
        self.session.consent(True)
        self.session.save_task()
        with self.assertRaises(AdapterError):
            self.session.receive_receipt(SavedRootRestoreReview('other', 'a'*64))
        self.assertEqual(self.session.state, 'failed')
        self.setUp()
        self.session.preview_task()
        with self.assertRaises(AdapterError):
            self.session.receive_preview(replace(self.selection, backup_id='other'))
        self.assertEqual(self.session.state, 'failed')

    def start_failed_save(self):
        self.ready()
        self.session.consent(True)
        self.session.save_task()
        self.session.fail()

    def test_status_after_uncertain_save_is_explicit_single_shot_and_read_only(self):
        from llm_manager.infrastructure.root_restore_store import RootRestoreExecutionView
        self.assertFalse(self.session.can_check_status)
        self.start_failed_save()
        self.assertTrue(self.session.can_check_status)
        request = self.session._request
        self.runner.result = replace(self.runner.result, stdout=fixture.wire(dict(
            status='execution_status', request_id=request.request_id, request_hash=request.request_hash,
            state='review_only', requires_attention=False, attempt=None, result=None)))
        self.session.clock = lambda: fixture.NOW + timedelta(days=1)
        task = self.session.status_task()
        with self.assertRaises(AdapterError): self.session.status_task()
        self.session.receive_status(task(self.token))
        self.assertEqual(self.session.history, RootRestoreExecutionView(None, None))
        self.assertEqual(self.session.state, 'checked')
        self.assertFalse(self.session.can_save)
        self.assertFalse(self.session.can_check_status)
        self.assertEqual([call.argv[2] for call in self.runner.calls], ['preview', 'status'])

    def test_failed_status_cannot_retry_or_accept_late_success(self):
        from llm_manager.infrastructure.root_restore_store import RootRestoreExecutionView
        self.start_failed_save()
        self.session.status_task()
        self.session.fail()
        self.assertFalse(self.session.can_check_status)
        with self.assertRaises(AdapterError): self.session.receive_status(RootRestoreExecutionView(None, None))
        with self.assertRaises(AdapterError): self.session.save_task()
        self.assertIsNone(self.session.history)

    def test_status_rejects_unrelated_attempt(self):
        from llm_manager.infrastructure.root_restore_store import RootRestoreExecutionView, RootRestoreAttempt
        self.start_failed_save()
        self.session.status_task()
        with self.assertRaises(AdapterError):
            self.session.receive_status(RootRestoreExecutionView(RootRestoreAttempt('other', 'a'*64, 'b'*64, fixture.NOW), None))
        self.assertIsNone(self.session.history)

    def test_production_factory_rejects_remote_wrong_host_and_root_without_io(self):
        with patch('llm_manager.ui.root_restore_review.os.getuid', return_value=1000):
            for host in (HostCandidate('ssh:x', HostKind.SSH, 'x'),
                         HostCandidate('local:wrong', HostKind.LOCAL, 'wrong')):
                with self.assertRaises(AdapterError): production_review_session(host, 'backup-1')
        import os
        host = HostCandidate('local:' + os.uname().nodename, HostKind.LOCAL, 'local')
        with patch('llm_manager.ui.root_restore_review.os.getuid', return_value=0):
            with self.assertRaises(AdapterError): production_review_session(host, 'backup-1')
        with patch('llm_manager.ui.root_restore_review.os.getuid', return_value=1000):
            session = production_review_session(host, 'backup-1')
        self.assertEqual(session.state, 'new')
