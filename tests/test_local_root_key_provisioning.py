import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.infrastructure.local_root_key_provisioning import ProvisionLocalRootKey
from llm_manager.infrastructure.root_backup_capture import LocalRootBackupKeys


class LocalRootKeyProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        options = dict(owner_uid=os.getuid(), owner_gid=os.getgid())
        self.provision = ProvisionLocalRootKey(self.fd, **options)
        self.provider = LocalRootBackupKeys(self.fd, **options)

    def test_explicit_provision_returns_id_only_and_key_is_stable(self):
        self.assertEqual(self.provision.execute('key-1', CancellationToken()), 'key-1')
        first = self.provider.get_key('key-1', 'local_root')
        self.assertEqual(len(first), 32)
        self.assertEqual(self.provider.get_key('key-1', 'local_root'), first)
        self.assertEqual(sorted(os.listdir(self.fd)), ['key-1.key', 'key-1.ready'])
        with self.assertRaises(AdapterError): self.provision.execute('key-1', CancellationToken())
        self.assertEqual(self.provider.get_key('key-1', 'local_root'), first)

    def test_read_never_creates_missing_key(self):
        with self.assertRaises(AdapterError): self.provider.get_key('key-1', 'local_root')
        self.assertEqual(os.listdir(self.fd), [])

    def test_cancel_invalid_id_and_bad_entropy_write_nothing(self):
        with self.assertRaises(OperationCancelled): self.provision.execute('key-1', CancellationToken(cancelled=True))
        with self.assertRaises(AdapterError): self.provision.execute('../key', CancellationToken())
        self.provision.random_bytes = lambda size: b'short'
        with self.assertRaises(AdapterError): self.provision.execute('key-1', CancellationToken())
        self.assertEqual(os.listdir(self.fd), [])

    def test_interrupted_write_blocks_both_read_and_reprovision(self):
        with patch('os.fsync', side_effect=OSError('injected')), self.assertRaises(AdapterError):
            self.provision.execute('key-1', CancellationToken())
        self.assertTrue(any(name.endswith('.pending') for name in os.listdir(self.fd)))
        with self.assertRaises(AdapterError): self.provider.get_key('key-1', 'local_root')
        with self.assertRaises(AdapterError): self.provision.execute('key-1', CancellationToken())

    def test_missing_tampered_and_symlink_marker_rejected(self):
        self.provision.execute('key-1', CancellationToken())
        marker = self.root / 'key-1.ready'
        marker.write_bytes(b'0' * 64)
        with self.assertRaises(AdapterError): self.provider.get_key('key-1', 'local_root')
        marker.unlink()
        with self.assertRaises(AdapterError): self.provider.get_key('key-1', 'local_root')
        marker.symlink_to(self.root / 'key-1.key')
        with self.assertRaises(AdapterError): self.provider.get_key('key-1', 'local_root')

    def test_reader_cannot_acquire_lock_during_provisioning(self):
        random_bytes = self.provision.random_bytes
        def observe(size):
            with self.assertRaises(AdapterError) as caught: self.provider.get_key('key-1', 'local_root')
            self.assertEqual(caught.exception.code, 'root_key_store_busy')
            return random_bytes(size)
        self.provision.random_bytes = observe
        self.provision.execute('key-1', CancellationToken())

    def test_ready_publication_failure_does_not_expose_usable_key(self):
        publish = self.provision._publish
        def fail(name, data, token):
            if name.endswith('.ready'): raise OSError('injected')
            return publish(name, data, token)
        with patch.object(self.provision, '_publish', side_effect=fail), self.assertRaises(AdapterError):
            self.provision.execute('key-1', CancellationToken())
        self.assertEqual(os.listdir(self.fd), ['key-1.key'])
        with self.assertRaises(AdapterError): self.provider.get_key('key-1', 'local_root')
