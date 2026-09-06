import fcntl
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure import root_restore_setup_cli as setup
from llm_manager.infrastructure.root_backup_capture import LocalRootBackupKeys
from llm_manager.infrastructure.root_apply_capture import PRODUCTION_KEY_ID


class RootRestoreSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        self.options = dict(owner_uid=os.getuid(), owner_gid=os.getgid())
        self.state = self.path / 'local-root-restore'

    def initialize(self):
        setup.initialize_empty_state(self.fd, **self.options)

    def test_empty_setup_produces_readable_key_and_never_replaces_it(self):
        # Existing helper state commonly has a safe shared 0755 parent.
        self.path.chmod(0o755)
        self.initialize()
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o755)
        self.assertEqual(sorted(p.name for p in self.state.iterdir()), sorted(setup.STATE_DIRECTORIES))
        key_fd = os.open(self.state / 'keys', os.O_RDONLY | os.O_DIRECTORY)
        try:
            key = LocalRootBackupKeys(key_fd, **self.options).get_key(PRODUCTION_KEY_ID, 'local_root')
            self.assertEqual(len(key), 32)
            with self.assertRaises(AdapterError) as caught: self.initialize()
            self.assertEqual(caught.exception.code, 'root_setup_existing_state')
            self.assertEqual(LocalRootBackupKeys(key_fd, **self.options).get_key(PRODUCTION_KEY_ID, 'local_root'), key)
        finally: os.close(key_fd)
        for path in self.state.rglob('*'):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700 if path.is_dir() else 0o600)

    def test_missing_key_with_backup_history_or_pending_data_never_generates(self):
        self.state.mkdir(mode=0o700)
        for name in setup.STATE_DIRECTORIES: (self.state / name).mkdir(mode=0o700)
        for name in setup.STATE_DIRECTORIES:
            evidence = self.state / name / 'retained-evidence'
            evidence.write_bytes(b'preserve')
            with patch.object(setup, 'ProvisionLocalRootKey') as provision:
                with self.assertRaises(AdapterError): self.initialize()
                provision.assert_not_called()
            self.assertEqual(evidence.read_bytes(), b'preserve')
            evidence.unlink()

    def test_symlink_and_unsafe_directory_are_not_repaired(self):
        self.state.mkdir(mode=0o700)
        elsewhere = self.path / 'elsewhere'; elsewhere.mkdir(mode=0o700)
        keys = self.state / 'keys'; keys.symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaises(OSError): self.initialize()
        self.assertEqual(list(elsewhere.iterdir()), [])
        keys.unlink(); keys.mkdir(mode=0o755)
        with self.assertRaises(AdapterError): self.initialize()
        self.assertEqual(keys.stat().st_mode & 0o777, 0o755)

    def test_concurrent_setup_refuses_and_empty_directory_only_retry_succeeds(self):
        self.state.mkdir(mode=0o700)
        fd = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(AdapterError) as caught: self.initialize()
            self.assertEqual(caught.exception.code, 'root_setup_busy')
        finally: os.close(fd)
        self.initialize()

    def test_partial_key_publication_is_retained_and_retry_refused(self):
        publish = setup.ProvisionLocalRootKey._publish
        def fail(instance, name, *args):
            if name.endswith('.ready'): raise OSError('private-sentinel')
            return publish(instance, name, *args)
        with patch.object(setup.ProvisionLocalRootKey, '_publish', fail):
            with self.assertRaises(AdapterError): self.initialize()
        key = self.state / 'keys' / (PRODUCTION_KEY_ID + '.key')
        original = key.read_bytes()
        with self.assertRaises(AdapterError): self.initialize()
        self.assertEqual(key.read_bytes(), original)

    def test_cli_rejects_nonroot_before_io_and_never_reports_private_failure(self):
        output = io.StringIO()
        with patch.object(setup.os, 'geteuid', return_value=1000), \
             patch.object(setup, '_open_fixed_directory') as opener, redirect_stdout(output):
            self.assertEqual(setup.main(['initialize']), 1)
            opener.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['error_code'], 'root_required')
        output = io.StringIO()
        with patch.object(setup, 'initialize_production', side_effect=OSError('private-sentinel')), redirect_stdout(output):
            self.assertEqual(setup.main(['initialize']), 1)
        self.assertNotIn('private-sentinel', output.getvalue())
        with patch.object(setup, 'initialize_production') as initialize, redirect_stdout(io.StringIO()):
            self.assertEqual(setup.main(['initialize']), 0)
            initialize.assert_called_once_with()

    def test_cli_accepts_no_path_key_or_repair_override(self):
        for args in ([], ['repair'], ['initialize', '/tmp/key'], ['initialize', '--key-id=x']):
            with patch.object(setup, 'initialize_production') as initialize, \
                 redirect_stdout(io.StringIO()), patch('sys.stderr', io.StringIO()):
                with self.assertRaises(SystemExit): setup.main(args)
                initialize.assert_not_called()
