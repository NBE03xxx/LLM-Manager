import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure.root_restore_audit import RootRestoreAuditLog
from llm_manager.infrastructure.root_restore_store import RootRestoreState
from tests.test_local_root_restore_protocol import NOW
from tests import test_root_restore_execution as fixture


class RootRestoreAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        self.audit = RootRestoreAuditLog(self.fd, owner_uid=os.getuid(), owner_gid=os.getgid(), clock=lambda: NOW)

    def start(self):
        self.audit.append('root_restore.started', 'restore-1', (('request_hash', 'a'*64),))

    def finish(self):
        self.audit.append('root_restore.finished', 'restore-1',
                          (('request_hash', 'a'*64), ('state', 'committed'), ('error_code', None)))

    def test_chain_roundtrip_and_immutable_events(self):
        self.start(); self.finish()
        events = self.audit.read_all()
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1].previous_hash, events[0].event_hash)
        self.assertEqual([p.stat().st_mode & 0o777 for p in self.root.iterdir()], [0o600]*3)
        with self.assertRaises(AdapterError): self.start()
        with self.assertRaises(AdapterError): self.finish()
        self.assertEqual(self.audit.read_all(), events)

    def test_unknown_fields_duplicates_and_unmatched_terminal_rejected(self):
        with self.assertRaises(AdapterError): self.finish()
        for fields in ((('request_hash', 'a'*64), ('content', 'private-sentinel')),
                       (('request_hash', 'a'*64), ('request_hash', 'a'*64)),
                       (('request_hash', 'bad'),)):
            with self.assertRaises(AdapterError): self.audit.append('root_restore.started', 'restore-1', fields)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_tail_deletion_and_head_tampering_are_detected(self):
        self.start(); self.finish()
        (self.root/'00000000000000000002.json').unlink()
        with self.assertRaises(AdapterError): self.audit.read_all()
        with self.assertRaises(AdapterError): self.start()

    def test_symlink_hardlink_and_mode_are_rejected(self):
        self.start()
        path = self.root/'00000000000000000001.json'
        path.chmod(0o644)
        with self.assertRaises(AdapterError): self.audit.read_all()
        path.chmod(0o600)
        other = self.root/'alias'
        os.link(path, other)
        with self.assertRaises(AdapterError): self.audit.read_all()
        other.unlink()
        path.unlink(); path.symlink_to('HEAD')
        with self.assertRaises(AdapterError): self.audit.read_all()

    def test_failed_publication_preserves_pending_and_blocks_append(self):
        with patch('os.fsync', side_effect=OSError('injected')), self.assertRaises(AdapterError): self.start()
        self.assertTrue(any(p.name.endswith('.pending') for p in self.root.iterdir()))
        with self.assertRaises(AdapterError): self.start()

    def test_event_published_without_head_blocks_append(self):
        original = self.audit._publish
        def publish(name, *args, **kwargs):
            if name == 'HEAD': raise OSError('injected')
            return original(name, *args, **kwargs)
        with patch.object(self.audit, '_publish', side_effect=publish), self.assertRaises(AdapterError): self.start()
        self.assertTrue((self.root/'00000000000000000001.json').exists())
        with self.assertRaises(AdapterError): self.audit.read_all()
        with self.assertRaises(AdapterError): self.start()

    def test_reader_and_writer_contend_with_independent_descriptions(self):
        with self.audit._locked(write=True):
            with self.assertRaises(AdapterError): self.audit.read_all()
            with self.assertRaises(AdapterError): self.start()
        self.start()


class RootRestoreAuditIntegrationTests(unittest.TestCase):
    setUp = fixture.RootRestoreExecutionTests.setUp
    run_capture = fixture.RootRestoreExecutionTests.run_capture
    prepare = fixture.RootRestoreExecutionTests.prepare
    make = fixture.RootRestoreExecutionTests.make
    run_restore = fixture.RootRestoreExecutionTests.run_restore

    def attach(self):
        self.make()
        directory = self.root/'strict-audit'
        directory.mkdir(mode=0o700)
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, fd)
        self.audit = RootRestoreAuditLog(fd, owner_uid=os.getuid(), owner_gid=os.getgid(), clock=lambda: NOW)
        self.coordinator.audit = self.audit
        return directory

    def test_real_restore_persists_strict_start_and_terminal_chain(self):
        self.attach()
        self.assertEqual(self.run_restore().state, RootRestoreState.COMMITTED)
        self.assertEqual([e.event_type for e in self.audit.read_all()], ['root_restore.started', 'root_restore.finished'])
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_unsafe_audit_stops_before_target_mutation(self):
        directory = self.attach()
        directory.chmod(0o777)
        result = self.run_restore()
        self.assertEqual(result.state, RootRestoreState.FAILED)
        self.assertEqual(self.target.read_bytes(), b'new current settings')
        self.assertEqual(self.service.calls, 0)
