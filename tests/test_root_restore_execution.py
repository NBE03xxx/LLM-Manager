import fcntl
import os
import unittest
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.infrastructure.audit import LocalAuditLog
from llm_manager.infrastructure.local_root_restore_preflight import CheckLocalRootRestore
from llm_manager.infrastructure.local_root_restore_protocol import RootRestoreFileState
from llm_manager.infrastructure.root_restore_execution import (
    ExecuteLocalRootRestore, SingleRootRestoreTarget, RootRestorePersistenceError,
)
from llm_manager.infrastructure.root_restore_store import RootRestoreState
from tests import test_root_backup_verification as fixture
from tests.test_local_root_restore_protocol import NOW
from tests.test_root_restore_service import Runner
from llm_manager.infrastructure.root_restore_service import RootRestoreOllamaService


class Service:
    def __init__(self): self.calls = 0; self.result = True
    def reload_restart_validate(self, restored_content, cancellation):
        self.calls += 1
        return self.result


class RootRestoreExecutionTests(unittest.TestCase):
    setUp = fixture.RootBackupVerificationTests.setUp
    run_capture = fixture.RootBackupVerificationTests.run_capture
    prepare = fixture.RootBackupVerificationTests.prepare

    def make(self, mode='replace'):
        if mode == 'remove':
            self.target.unlink()
            op = replace(self.request.operations[0], before_hash=None)
            self.request = replace(self.request, operations=(op,) + self.request.operations[1:]).with_hash()
        self.prepare()
        if mode == 'create':
            self.target.unlink()
            intent = replace(self.review.approved_request, request_id='restore-create', current=RootRestoreFileState(False)).with_hash()
            self.review = replace(self.review, approved_request=intent)
            self.store.save_review(self.review, CancellationToken())
        self.audit = LocalAuditLog(self.root / 'audit')
        self.service = Service()
        self.backend = SingleRootRestoreTarget(self.source, owner_uid=os.getuid(), owner_gid=os.getgid())
        self.coordinator = ExecuteLocalRootRestore(
            self.store, CheckLocalRootRestore(self.port, clock=lambda: NOW), self.reader,
            self.verifier, self.backend, self.audit, self.service, clock=lambda: NOW,
        )
        self.token = CancellationToken()

    def run_restore(self):
        intent = self.review.approved_request
        return self.coordinator.execute(intent, expected_hash=intent.request_hash, caller_uid=1000,
                                        host_id=intent.host_id, cancellation=self.token)

    def test_replace_restores_original_after_attempt_and_start_audit(self):
        self.make()
        append = self.audit.append
        def inspect(event, correlation, fields):
            if event == 'root_restore.started':
                self.assertFalse(self.store.request_is_unused(correlation, CancellationToken()))
                self.assertEqual(self.target.read_bytes(), b'new current settings')
            return append(event, correlation, fields)
        with patch.object(self.audit, 'append', side_effect=inspect): result = self.run_restore()
        self.assertEqual(result.state, RootRestoreState.COMMITTED)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(self.service.calls, 1)
        self.assertEqual(self.store.load_execution(result.request_id, CancellationToken()).result, result)
        with self.assertRaises(AdapterError): self.run_restore()

    def test_create_restores_absent_current_target(self):
        self.make('create')
        self.assertEqual(self.run_restore().state, RootRestoreState.COMMITTED)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_remove_restores_original_absence(self):
        self.make('remove')
        self.assertEqual(self.run_restore().state, RootRestoreState.COMMITTED)
        self.assertFalse(self.target.exists())

    def test_start_audit_failure_prevents_mutation_and_consumes_attempt(self):
        self.make()
        with patch.object(self.audit, 'append', side_effect=OSError('injected')):
            result = self.run_restore()
        self.assertEqual(result.state, RootRestoreState.FAILED)
        self.assertEqual(self.target.read_bytes(), b'new current settings')
        self.assertEqual(self.service.calls, 0)
        self.assertFalse(self.store.request_is_unused(result.request_id, CancellationToken()))

    def test_changed_target_after_start_audit_is_not_overwritten(self):
        self.make()
        append = self.audit.append
        def change(event, correlation, fields):
            append(event, correlation, fields)
            if event == 'root_restore.started': self.target.write_bytes(b'external change')
        with patch.object(self.audit, 'append', side_effect=change): result = self.run_restore()
        self.assertEqual(result.state, RootRestoreState.FAILED)
        self.assertEqual(self.target.read_bytes(), b'external change')

    def test_mutation_failure_is_unknown_without_retry(self):
        self.make()
        with patch.object(self.backend, 'restore', side_effect=OSError('injected')) as mutate:
            result = self.run_restore()
        self.assertEqual(result.state, RootRestoreState.UNKNOWN)
        self.assertEqual(mutate.call_count, 1)
        self.assertEqual(self.service.calls, 0)
        with self.assertRaises(AdapterError): self.run_restore()

    def test_target_directory_fsync_failure_is_unknown_even_after_replace(self):
        self.make()
        fsync = os.fsync
        def fail(fd):
            if fd == self.source: raise OSError('injected target durability failure')
            return fsync(fd)
        with patch('os.fsync', side_effect=fail): result = self.run_restore()
        self.assertEqual(result.state, RootRestoreState.UNKNOWN)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(self.service.calls, 0)

    def test_target_changed_during_service_validation_is_not_committed(self):
        self.make()
        def change(restored_content, cancellation):
            self.target.write_bytes(b'changed by external actor')
            return True
        with patch.object(self.service, 'reload_restart_validate', side_effect=change):
            result = self.run_restore()
        self.assertEqual(result.state, RootRestoreState.UNKNOWN)
        self.assertEqual(self.target.read_bytes(), b'changed by external actor')

    def test_service_failure_records_disk_restore_without_automatic_rollback(self):
        self.make()
        self.service.result = False
        result = self.run_restore()
        self.assertEqual(result.state, RootRestoreState.FAILED)
        self.assertEqual(result.error_code, 'service_validation_failed')
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_real_service_validation_logic_is_connected_to_coordinator(self):
        self.make()
        runner = Runner()
        self.coordinator.service = RootRestoreOllamaService(runner)
        result = self.run_restore()
        self.assertEqual(result.state, RootRestoreState.COMMITTED)
        self.assertEqual(len(runner.calls), 5)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_cancel_after_mutation_still_persists_unknown_result(self):
        self.make()
        restore = self.backend.restore
        def cancel(*args, **kwargs):
            restore(*args, **kwargs)
            self.token.cancel()
        with patch.object(self.backend, 'restore', side_effect=cancel): result = self.run_restore()
        self.assertEqual(result.state, RootRestoreState.UNKNOWN)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(self.store.load_execution(result.request_id, CancellationToken()).result, result)

    def test_result_persistence_failure_retains_attempt_and_reports_unpersisted(self):
        self.make()
        with patch.object(self.store, 'finish', side_effect=OSError('injected')), self.assertRaises(RootRestorePersistenceError):
            self.run_restore()
        view = self.store.load_execution(self.review.approved_request.request_id, CancellationToken())
        self.assertTrue(view.requires_attention)
        self.assertIsNone(view.result)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_terminal_audit_failure_is_not_committed(self):
        self.make()
        append = self.audit.append
        def fail(event, correlation, fields):
            if event == 'root_restore.finished': raise OSError('injected')
            return append(event, correlation, fields)
        with patch.object(self.audit, 'append', side_effect=fail): result = self.run_restore()
        self.assertEqual(result.state, RootRestoreState.UNKNOWN)
        self.assertEqual(result.error_code, 'terminal_audit_failed')

    def test_target_lock_blocks_another_restore_before_attempt(self):
        self.make()
        independent = os.open(self.root / 'source', os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(independent, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(AdapterError): self.run_restore()
        finally: os.close(independent)
        self.assertTrue(self.store.request_is_unused(self.review.approved_request.request_id, CancellationToken()))

    def test_expiry_during_staging_prevents_final_replace(self):
        self.make()
        fsync = os.fsync
        def expire(fd):
            result = fsync(fd)
            # Only the restore staging FD lives in the target parent.
            try: path = os.readlink('/proc/self/fd/' + str(fd))
            except OSError: path = ''
            if '.llm-restore-' in path:
                self.coordinator.clock = lambda: NOW + timedelta(minutes=3)
            return result
        with patch('os.fsync', side_effect=expire): result = self.run_restore()
        self.assertEqual(result.state, RootRestoreState.UNKNOWN)
        self.assertEqual(self.target.read_bytes(), b'new current settings')
        self.assertTrue(any(path.name.startswith('.llm-restore-') for path in self.target.parent.iterdir()))
