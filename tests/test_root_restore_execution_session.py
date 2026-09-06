import os
import unittest
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

from llm_manager.application.errors import AdapterError
from llm_manager.application.host_discovery import HostCandidate
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.enums import HostKind
from llm_manager.infrastructure.root_restore_execute_client import RootRestoreExecutionUnconfirmed
from llm_manager.infrastructure.root_restore_store import (
    RootRestoreAttempt, RootRestoreExecutionView, RootRestoreResult, RootRestoreState,
)
from llm_manager.ui.root_restore_execution import (
    RejectedRootRestore, RootRestoreExecutionSession, UnconfirmedRootRestore,
    production_execution_session,
)
from tests.test_local_root_restore_protocol import NOW, request


class ExecuteClient:
    caller_uid = 1000
    host_id = 'local:host'
    def __init__(self, outcome): self.outcome, self.calls = outcome, 0
    def execute(self, request, token):
        self.calls += 1
        if isinstance(self.outcome, Exception): raise self.outcome
        return self.outcome


class StatusClient:
    def __init__(self, history): self.history, self.calls = history, 0
    def status(self, request, token): self.calls += 1; return self.history


class RootRestoreExecutionSessionTests(unittest.TestCase):
    def setUp(self):
        self.request = request()
        self.result = RootRestoreResult(
            self.request.request_id, self.request.request_hash, 'a' * 64,
            RootRestoreState.COMMITTED, NOW, None,
        )
        self.execute = ExecuteClient(self.result)
        self.status = StatusClient(RootRestoreExecutionView(None, None))
        self.session = RootRestoreExecutionSession(
            self.execute, self.status, self.request, clock=lambda: NOW,
        )
        self.token = CancellationToken()

    def execute_once(self):
        return self.session.execute_task()(self.token)

    def test_exact_hash_consent_allows_one_execution_and_bound_committed_result(self):
        self.assertFalse(self.session.can_execute)
        with self.assertRaises(AdapterError): self.session.execute_task()
        self.session.consent(True)
        self.assertTrue(self.session.can_execute)
        task = self.session.execute_task()
        with self.assertRaises(AdapterError): self.session.execute_task()
        self.session.receive_execution(task(self.token))
        self.assertEqual(self.session.state, 'committed')
        self.assertEqual(self.session.result, self.result)
        self.assertEqual(self.execute.calls, 1)
        self.assertFalse(self.session.can_execute)

    def test_uncheck_changed_hash_expiry_and_clock_regression_clear_consent(self):
        self.session.consent(True); self.session.consent(False)
        self.assertFalse(self.session.can_execute)
        self.session.consent(True)
        self.session.request = replace(self.request, request_hash='f' * 64)
        self.assertFalse(self.session.can_execute)
        for now in (NOW + timedelta(minutes=5), NOW - timedelta(microseconds=1)):
            self.setUp(); self.session.consent(True); self.session.clock = lambda now=now: now
            self.assertFalse(self.session.can_execute)
            self.assertEqual(self.session.state, 'expired')
            self.assertEqual(self.execute.calls, 0)

    def test_failed_and_unknown_terminal_results_are_final_without_status_retry(self):
        for state, code, expected in ((RootRestoreState.FAILED, 'service_validation_failed', 'failed_result'),
                                      (RootRestoreState.UNKNOWN, 'mutation_failed', 'unknown_result')):
            self.setUp()
            self.execute.outcome = replace(self.result, state=state, error_code=code)
            self.session.consent(True)
            self.session.receive_execution(self.execute_once())
            self.assertEqual(self.session.state, expected)
            self.assertFalse(self.session.can_check_status)
            self.assertFalse(self.session.can_execute)

    def test_unconfirmed_execution_allows_one_status_read_and_no_resend(self):
        self.execute.outcome = RootRestoreExecutionUnconfirmed(
            self.request.request_id, self.request.request_hash, RootRestoreState.UNKNOWN,
        )
        self.session.consent(True)
        outcome = self.execute_once()
        self.assertIsInstance(outcome, UnconfirmedRootRestore)
        self.session.receive_execution(outcome)
        self.assertTrue(self.session.can_check_status)
        task = self.session.status_task()
        with self.assertRaises(AdapterError): self.session.status_task()
        self.session.receive_status(task(self.token))
        self.assertEqual(self.session.state, 'checked')
        self.assertEqual(self.session.history, RootRestoreExecutionView(None, None))
        self.assertEqual(self.execute.calls, 1)
        self.assertEqual(self.status.calls, 1)

    def test_preexecution_rejection_and_worker_failure_never_resend(self):
        self.execute.outcome = AdapterError('privilege_denied', 'private-sentinel')
        self.session.consent(True)
        outcome = self.execute_once()
        self.assertEqual(outcome, RejectedRootRestore('privilege_denied'))
        self.session.receive_execution(outcome)
        self.assertEqual(self.session.state, 'rejected')
        self.assertFalse(self.session.can_execute)
        self.assertFalse(self.session.can_check_status)
        self.setUp(); self.session.consent(True); self.session.execute_task()
        self.session.worker_failed('executing')
        self.assertEqual(self.session.state, 'unconfirmed')
        self.assertTrue(self.session.can_check_status)
        self.assertFalse(self.session.can_execute)

    def test_unrelated_result_unconfirmed_and_history_are_rejected(self):
        cases = (
            replace(self.result, request_id='other'),
            UnconfirmedRootRestore('other', self.request.request_hash, None),
            object(),
        )
        for outcome in cases:
            self.setUp(); self.session.consent(True); self.session.execute_task()
            with self.subTest(outcome=outcome), self.assertRaises(AdapterError):
                self.session.receive_execution(outcome)
            self.assertEqual(self.session.state, 'failed')
        self.setUp(); self.execute.outcome = RootRestoreExecutionUnconfirmed(
            self.request.request_id, self.request.request_hash)
        self.session.consent(True); self.session.receive_execution(self.execute_once()); self.session.status_task()
        wrong = RootRestoreExecutionView(
            RootRestoreAttempt('other', self.request.request_hash, 'a' * 64, NOW), None,
        )
        with self.assertRaises(AdapterError): self.session.receive_status(wrong)
        self.assertEqual(self.session.state, 'status_failed')

    def test_production_factory_rejects_remote_wrong_host_and_root_before_clients(self):
        local_id = 'local:' + os.uname().nodename
        hosts = (HostCandidate('ssh:x', HostKind.SSH, 'x'),
                 HostCandidate('local:wrong', HostKind.LOCAL, 'wrong'))
        with patch('llm_manager.ui.root_restore_execution.os.getuid', return_value=1000), \
             patch('llm_manager.ui.root_restore_execution.RootRestoreExecuteClient') as client:
            for host in hosts:
                with self.assertRaises(AdapterError): production_execution_session(host, self.request)
            client.assert_not_called()
        host = HostCandidate(local_id, HostKind.LOCAL, 'local')
        with patch('llm_manager.ui.root_restore_execution.os.getuid', return_value=0), \
             patch('llm_manager.ui.root_restore_execution.RootRestoreExecuteClient') as client:
            with self.assertRaises(AdapterError): production_execution_session(host, self.request)
            client.assert_not_called()


if __name__ == '__main__': unittest.main()
