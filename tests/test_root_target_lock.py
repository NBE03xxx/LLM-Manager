"""Real directory flock gates across helper Apply/rollback and root restore."""
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.infrastructure.helper_backend import LocalSystemHelperBackend
from llm_manager.infrastructure.helper_cli import run_helper
from llm_manager.infrastructure.helper_executor import DeclaredHelperExecutor
from llm_manager.infrastructure.helper_receipts import HelperReceiptStore
from llm_manager.infrastructure.helper_protocol import HelperOperationKind
from llm_manager.infrastructure.helper_staging import HelperStagingStore
from llm_manager.infrastructure.root_restore_execution import SingleRootRestoreTarget
from llm_manager.planning.ollama import DROP_IN_PATH
from tests.test_helper_executor import _request
from tests.test_helper_cli import _stage


class RootTargetLockTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / DROP_IN_PATH.lstrip('/')
        self.path.parent.mkdir(parents=True)
        self.path.parent.chmod(0o755)
        self.path.write_bytes(b'old')
        self.path.chmod(0o644)
        self.fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        self.target = SingleRootRestoreTarget(self.fd, owner_uid=os.getuid(), owner_gid=os.getgid())
        self.commands = []
        self.backend = LocalSystemHelperBackend(root=self.root, sandbox=True, service_runner=self.service)
        self.staging = HelperStagingStore(self.root / 'stage')

    def service(self, argv):
        self.commands.append(argv)
        return 0

    def execute(self, kind=HelperOperationKind.ATOMIC_REPLACE, before=b'old'):
        request = _request(before, b'new')
        operation = replace(request.operations[0], kind=kind)
        if kind == HelperOperationKind.REMOVE_CREATED_FILE:
            operation = replace(operation, staged_content_hash=None, expected_mode=None,
                                expected_uid=None, expected_gid=None)
        request = replace(request, operation_id=kind.value, operations=(operation,) + request.operations[1:]).with_hash()
        if kind != HelperOperationKind.REMOVE_CREATED_FILE:
            self.staging.stage(request, operation.operation_id, b'new')
        return DeclaredHelperExecutor(self.staging, self.backend).execute(request, request.request_hash)

    def test_restore_lock_blocks_apply_and_both_rollback_operations_before_read(self):
        for kind in (HelperOperationKind.ATOMIC_REPLACE, HelperOperationKind.RESTORE_FILE,
                     HelperOperationKind.REMOVE_CREATED_FILE):
            with self.subTest(kind=kind):
                original_read = self.backend.read_file
                self.backend.read_file = lambda target: self.fail('read before acquiring lock')
                try:
                    with self.target.locked(CancellationToken()):
                        result = self.execute(kind)
                    self.assertEqual(result[0].error_code, 'helper_target_busy')
                    self.assertEqual([x.completed for x in result], [False, False, False])
                    self.assertEqual(result[1].error_code, 'not_executed')
                    self.assertEqual(self.path.read_bytes(), b'old')
                    self.assertEqual(self.commands, [])
                finally:
                    self.backend.read_file = original_read

    def test_helper_holds_lock_during_before_check_write_and_each_service_command(self):
        observed = []
        def check():
            with self.assertRaises(AdapterError) as error:
                with self.target.locked(CancellationToken()):
                    self.fail('competing restore acquired helper lock')
            self.assertEqual(error.exception.code, 'root_restore_target_busy')
            observed.append(True)
        read, write = self.backend.read_file, self.backend.atomic_write
        def locked_read(target):
            check()
            return read(target)
        def locked_write(*args):
            check()
            return write(*args)
        self.backend.read_file, self.backend.atomic_write = locked_read, locked_write
        self.backend.service_runner = lambda argv: check() or 0
        self.assertTrue(all(x.completed for x in self.execute()))
        self.assertEqual(len(observed), 4)
        with self.target.locked(CancellationToken()):
            pass

    def test_another_process_contends_on_same_inode(self):
        script = """
import fcntl, os, sys
fd = os.open(sys.argv[1], os.O_RDONLY | os.O_DIRECTORY)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit(7)
sys.exit(0)
"""
        with self.backend.locked():
            result = subprocess.run((sys.executable, '-I', '-c', script, str(self.path.parent)),
                                    capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 7, result.stderr)
        result = subprocess.run((sys.executable, '-I', '-c', script, str(self.path.parent)),
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_service_failure_releases_lock_and_stops_remaining_commands(self):
        self.backend.service_runner = lambda argv: 1
        result = self.execute()
        self.assertEqual([x.completed for x in result], [True, False, False])
        self.assertEqual(self.path.read_bytes(), b'new')
        with self.target.locked(CancellationToken()):
            pass

    def test_abandoned_restore_staging_blocks_helper_without_cleanup(self):
        pending = self.path.parent / '.llm-restore-injected.pending'
        pending.write_bytes(b'evidence')
        result = self.execute()
        self.assertEqual(result[0].error_code, 'root_restore_staging_incomplete')
        self.assertEqual(self.path.read_bytes(), b'old')
        self.assertEqual(pending.read_bytes(), b'evidence')
        self.assertEqual(self.commands, [])

    def test_first_apply_creates_parent_and_rollback_removes_created_file(self):
        self.path.unlink()
        self.path.parent.rmdir()
        self.assertTrue(all(x.completed for x in self.execute(before=None)))
        self.assertEqual(self.path.read_bytes(), b'new')
        result = self.execute(HelperOperationKind.REMOVE_CREATED_FILE, before=b'new')
        self.assertTrue(all(x.completed for x in result))
        self.assertFalse(self.path.exists())

    def test_stale_target_rejected_under_lock_and_lock_released(self):
        self.path.write_bytes(b'changed')
        result = self.execute()
        self.assertEqual(result[0].error_code, 'stale_helper_target')
        self.assertEqual(self.commands, [])
        with self.target.locked(CancellationToken()):
            pass

    def test_unsafe_directory_rejected_before_commands(self):
        self.path.parent.chmod(0o777)
        result = self.execute()
        self.assertEqual(result[0].error_code, 'unsafe_target')
        self.assertEqual(self.path.read_bytes(), b'old')
        self.assertEqual(self.commands, [])

    def test_expiry_after_acquisition_rejects_before_target_read(self):
        request = _request(b'old', b'new')
        self.staging.stage(request, 'write-1', b'new')
        self.backend.read_file = lambda target: self.fail('expired request observed target')
        with patch('llm_manager.infrastructure.helper_executor.utc_now',
                   side_effect=[request.expires_at - timedelta(seconds=1), request.expires_at]):
            result = DeclaredHelperExecutor(self.staging, self.backend).execute(request, request.request_hash)
        self.assertFalse(any(x.completed for x in result))
        self.assertEqual(self.path.read_bytes(), b'old')
        self.assertEqual(self.commands, [])
        with self.target.locked(CancellationToken()):
            pass

    def test_cli_persists_busy_failure_and_rejects_replay_after_unlock(self):
        runtime = self.root / 'runtime'
        request, _ = _stage(runtime, os.getuid())
        receipts = HelperReceiptStore(self.root / 'receipts', sandbox=True)
        def invoke():
            return run_helper(request.operation_id, request.request_hash,
                              environ={'PKEXEC_UID': str(os.getuid())}, runtime_base=runtime,
                              backend=self.backend, receipts=receipts, effective_uid=0)
        with self.target.locked(CancellationToken()):
            result = invoke()
        self.assertEqual(result[0].error_code, 'helper_target_busy')
        self.assertIsNotNone(receipts.load(request.operation_id))
        with self.assertRaises(AdapterError) as error:
            invoke()
        self.assertEqual(error.exception.code, 'replayed_request')
        self.assertEqual(self.path.read_bytes(), b'old')
        self.assertEqual(self.commands, [])


if __name__ == '__main__':
    unittest.main()
