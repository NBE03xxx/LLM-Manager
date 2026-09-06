import hashlib
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.infrastructure.root_backup_evidence import (
    MAX_RECORD_BYTES, MAX_CIPHERTEXT_BYTES, MAX_INVENTORY_ITEMS,
    RootBackupEvidence, RootBackupEvidenceReader,
    decode_evidence, encode_evidence, open_production_directory,
)
from tests.test_local_root_restore_protocol import NOW, request


class RootBackupEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        self.payload = b'opaque encrypted fixture'
        self.record = RootBackupEvidence(
            'llm-manager.root-backup-origin/1', 'backup-1', 'local:host', 'a' * 64,
            request().target, request().backup,
            hashlib.sha256(self.payload).hexdigest(), 'root-key-1', NOW, source_manifest_hash='b' * 64,
        ).with_hash()
        self.write('backup-1.json', encode_evidence(self.record))
        self.write('backup-1.bin', self.payload)
        self.reader = RootBackupEvidenceReader(self.fd, owner_uid=os.getuid(), owner_gid=os.getgid())

    def write(self, name, content):
        path = self.root / name
        path.write_bytes(content)
        path.chmod(0o600)
        return path

    def read(self, record=None, **kwargs):
        record = record or self.record
        return self.reader.read(record.backup_id, record.record_hash, kwargs.get('token', CancellationToken()))

    def test_reads_canonical_record_and_exact_ciphertext_without_writing(self):
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir()}
        self.assertEqual(self.read(), (self.record, self.payload))
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir()})

    def test_lists_bounded_stable_inventory_without_payload_or_key_metadata(self):
        items = self.reader.list_inventory(CancellationToken())
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual((item.backup_id, item.host_id, item.original),
                         (self.record.backup_id, self.record.host_id, self.record.original))
        self.assertEqual(item.record_hash, self.record.record_hash)
        self.assertFalse(hasattr(item, 'key_id'))
        self.assertFalse(hasattr(item, 'ciphertext_hash'))

    def test_inventory_rejects_orphans_unknown_entries_and_excess_count(self):
        for name in ('orphan.bin', 'unexpected', 'partial.pending'):
            path = self.write(name, b'x')
            with self.subTest(name=name), self.assertRaises(AdapterError):
                self.reader.list_inventory(CancellationToken())
            path.unlink()
        for index in range(MAX_INVENTORY_ITEMS):
            record = replace(self.record, backup_id=f'extra-{index}').with_hash()
            self.write(record.backup_id + '.json', encode_evidence(record))
            self.write(record.backup_id + '.bin', self.payload)
        with self.assertRaises(AdapterError) as caught:
            self.reader.list_inventory(CancellationToken())
        self.assertEqual(caught.exception.code, 'root_backup_inventory_too_large')

    def test_inventory_cancel_and_entry_change_are_fail_closed(self):
        with self.assertRaises(OperationCancelled):
            self.reader.list_inventory(CancellationToken(cancelled=True))
        real = self.reader._read
        def change(*args):
            value = real(*args)
            self.write('unexpected', b'x')
            return value
        with patch.object(self.reader, '_read', side_effect=change), self.assertRaises(AdapterError):
            self.reader.list_inventory(CancellationToken())

    def test_manifest_required_and_inspect_does_not_relax_read_binding(self):
        self.assertEqual(self.reader.inspect('backup-1', CancellationToken()), (self.record, self.payload))
        with self.assertRaises(AdapterError):
            self.reader.read('backup-1', None, CancellationToken())
        legacy = json.loads(encode_evidence(self.record))
        del legacy['source_manifest_hash']
        with self.assertRaises(AdapterError): decode_evidence(json.dumps(legacy).encode())
        with self.assertRaises(AdapterError):
            encode_evidence(replace(self.record, source_manifest_hash='').with_hash())

    def test_absent_original_requires_no_payload_entry(self):
        record = replace(self.record, original=replace(request().backup, exists=False,
                         sha256=None, mode=None, uid=None, gid=None), ciphertext_hash=None, key_id=None).with_hash()
        self.write('backup-1.json', encode_evidence(record))
        with self.assertRaises(AdapterError):
            self.read(record)
        (self.root / 'backup-1.bin').unlink()
        self.assertEqual(self.read(record), (record, None))
        (self.root / 'backup-1.bin').symlink_to(self.root / 'missing')
        with self.assertRaises(AdapterError):
            self.read(record)

    def test_rejects_record_or_ciphertext_tampering_and_wrong_expected_hash(self):
        self.write('backup-1.bin', b'changed ciphertext')
        with self.assertRaises(AdapterError):
            self.read()
        self.write('backup-1.bin', self.payload)
        self.write('backup-1.json', encode_evidence(self.record) + b'\n')
        with self.assertRaises(AdapterError):
            self.read()
        self.write('backup-1.json', encode_evidence(self.record))
        with self.assertRaises(AdapterError):
            self.reader.read('backup-1', 'f' * 64, CancellationToken())

    def test_rejects_symlink_hardlink_fifo_and_directory_records(self):
        name = self.root / 'backup-1.json'
        data = name.read_bytes()
        other = self.write('other', data)
        for kind in ('symlink', 'hardlink', 'fifo', 'directory'):
            name.unlink()
            if kind == 'symlink': name.symlink_to(other)
            elif kind == 'hardlink': os.link(other, name)
            elif kind == 'fifo': os.mkfifo(name, 0o600)
            else: name.mkdir(mode=0o700)
            with self.subTest(kind=kind), self.assertRaises(AdapterError):
                self.read()
            if kind == 'directory':
                name.rmdir()
                self.write(name.name, data)
            else:
                name.unlink()
                self.write(name.name, data)

    def test_rejects_payload_symlink_and_unsafe_modes(self):
        payload = self.root / 'backup-1.bin'
        payload.unlink()
        payload.symlink_to(self.write('other', self.payload))
        with self.assertRaises(AdapterError): self.read()
        payload.unlink()
        self.write(payload.name, self.payload)
        for path, mode in ((payload, 0o644), (self.root / 'backup-1.json', 0o666), (self.root, 0o755)):
            original = path.stat().st_mode & 0o777
            path.chmod(mode)
            with self.subTest(path=path), self.assertRaises(AdapterError): self.read()
            path.chmod(original)

    def test_rejects_wrong_directory_owner_and_record_owner(self):
        reader = RootBackupEvidenceReader(self.fd, owner_uid=os.getuid() + 1)
        with self.assertRaises(AdapterError):
            reader.read('backup-1', self.record.record_hash, CancellationToken())
        original = os.fstat
        def wrong_owner(fd):
            value = original(fd)
            if fd != self.fd:
                fields = list(value)
                fields[4] = os.getuid() + 1
                return os.stat_result(fields)
            return value
        with patch('os.fstat', side_effect=wrong_owner), self.assertRaises(AdapterError):
            self.read()

    def test_rejects_oversized_record_before_read(self):
        self.write('backup-1.json', b'x' * (MAX_RECORD_BYTES + 1))
        with patch('os.read', side_effect=AssertionError('must reject before read')):
            with self.assertRaises(AdapterError): self.read()

    def test_rejects_wrong_group_and_oversized_payload(self):
        reader = RootBackupEvidenceReader(self.fd, owner_uid=os.getuid(), owner_gid=os.getgid() + 1)
        with self.assertRaises(AdapterError):
            reader.read('backup-1', self.record.record_hash, CancellationToken())
        with (self.root / 'backup-1.bin').open('r+b') as payload:
            payload.truncate(MAX_CIPHERTEXT_BYTES + 1)
        with self.assertRaises(AdapterError): self.read()

    def test_rejects_record_replaced_while_reading(self):
        real_read = os.read
        replaced = False
        def swap(fd, size):
            nonlocal replaced
            data = real_read(fd, size)
            if data and not replaced:
                replaced = True
                replacement = self.write('replacement', encode_evidence(self.record))
                replacement.replace(self.root / 'backup-1.json')
            return data
        with patch('os.read', side_effect=swap), self.assertRaises(AdapterError):
            self.read()

    def test_cancel_before_and_during_read_leaves_files_intact(self):
        with self.assertRaises(OperationCancelled): self.read(token=CancellationToken(cancelled=True))
        token = CancellationToken()
        real_read = os.read
        def cancel(fd, size):
            data = real_read(fd, size)
            token.cancel()
            return data
        with patch('os.read', side_effect=cancel), self.assertRaises(OperationCancelled): self.read(token=token)
        self.assertEqual(self.read(), (self.record, self.payload))

    def test_record_codec_rejects_unknown_fields_types_and_binding(self):
        base = json.loads(encode_evidence(self.record))
        for value in ({**base, 'shell': '/bin/sh'}, {**base, 'backup_id': 'other'},
                      {**base, 'key_id': None}, {**base, 'original': {**base['original'], 'uid': False}},
                      {**base, 'captured_at': '2026-09-05T00:00:00'}):
            with self.subTest(value=value), self.assertRaises(AdapterError):
                decode_evidence(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())
        for changes in ({'target': '/etc/passwd'}, {'backup_id': '../escape'},
                        {'source_apply_request_hash': 'bad'}, {'key_id': None}):
            with self.subTest(changes=changes), self.assertRaises(AdapterError):
                encode_evidence(replace(self.record, **changes).with_hash())

    def test_fixed_path_opener_rejects_writable_ancestor(self):
        with patch('llm_manager.infrastructure.root_backup_evidence.STORE_PATH', str(self.root)):
            with self.assertRaises(AdapterError): open_production_directory()


if __name__ == '__main__': unittest.main()
