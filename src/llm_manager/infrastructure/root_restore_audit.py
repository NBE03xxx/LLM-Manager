"""Strict root restore audit chain; borrow a pre-provisioned directory FD."""
from contextlib import contextmanager
from dataclasses import replace
import fcntl
import json
import os
import re
import uuid

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import utc_now
from .audit import AuditEvent, _bytes, _decode, _hash
from .root_backup_evidence import RootBackupEvidenceReader, _ID, _HASH, _open_fixed_directory

AUDIT_PATH = '/var/lib/llm-manager/local-root-restore/audit'
MAX_EVENTS = 10000


def open_production_audit_directory():
    return _open_fixed_directory(AUDIT_PATH)


def _reject():
    raise AdapterError('invalid_root_restore_audit', 'root restore audit requires reconciliation')


def _fields(event_type, correlation_id, fields):
    if not isinstance(correlation_id, str) or not _ID.fullmatch(correlation_id):
        _reject()
    if event_type not in ('root_restore.started', 'root_restore.finished'):
        _reject()
    try:
        values = dict(fields)
    except (TypeError, ValueError):
        _reject()
    expected = {'request_hash'} if event_type.endswith('.started') else {'request_hash', 'state', 'error_code'}
    if len(values) != len(fields) or set(values) != expected:
        _reject()
    if not isinstance(values['request_hash'], str) or not _HASH.fullmatch(values['request_hash']):
        _reject()
    if 'state' in values:
        state, code = values['state'], values['error_code']
        if state not in ('committed', 'failed', 'unknown'):
            _reject()
        if state == 'committed':
            if code is not None: _reject()
        elif not isinstance(code, str) or not re.fullmatch('[a-z][a-z0-9_]{0,63}', code):
            _reject()
    return tuple(sorted(values.items()))


class RootRestoreAuditLog:
    def __init__(self, directory_fd, *, owner_uid=0, owner_gid=0, clock=utc_now):
        self.fd, self.clock = directory_fd, clock
        self.reader = RootBackupEvidenceReader(directory_fd, owner_uid=owner_uid, owner_gid=owner_gid)

    @contextmanager
    def _locked(self, write=False):
        self.reader._directory()
        fd = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=self.fd)
        try:
            try:
                fcntl.flock(fd, (fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            except OSError as error:
                raise AdapterError('root_restore_audit_busy', 'root restore audit is busy') from error
            yield
            self.reader._directory()
        except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError) as error:
            raise AdapterError('invalid_root_restore_audit', 'root restore audit requires reconciliation') from error
        finally:
            os.close(fd)

    def read_all(self):
        with self._locked():
            return self._read()

    def _read(self):
        names = set(os.listdir(self.fd))
        if len(names) > MAX_EVENTS + 1: _reject()
        if not names: return ()
        events = []
        previous = None
        records = sorted(names - {'HEAD'})
        if 'HEAD' not in names: _reject()
        for sequence, name in enumerate(records, 1):
            if name != f'{sequence:020d}.json': _reject()
            content = self.reader._read_file(name, 16384, CancellationToken())
            event = _decode(json.loads(content))
            if (event.sequence != sequence or event.previous_hash != previous or
                    event.event_hash != _hash(event) or content != _bytes(event) or
                    event.fields != _fields(event.event_type, event.correlation_id, event.fields)):
                _reject()
            self._transition(events, event)
            events.append(event)
            previous = event.event_hash
        if not events: _reject()
        head = self.reader._read_file('HEAD', 128, CancellationToken())
        if head != f'{len(events)} {previous}\n'.encode('ascii'): _reject()
        return tuple(events)

    @staticmethod
    def _transition(events, event):
        if events and event.created_at < events[-1].created_at: _reject()
        prior = [item for item in events if item.correlation_id == event.correlation_id]
        if event.event_type == 'root_restore.started':
            if prior: _reject()
        elif (len(prior) != 1 or prior[0].event_type != 'root_restore.started' or
              dict(prior[0].fields)['request_hash'] != dict(event.fields)['request_hash']):
            _reject()

    def append(self, event_type, correlation_id, fields):
        fields = _fields(event_type, correlation_id, fields)
        with self._locked(write=True):
            events = self._read()
            if len(events) >= MAX_EVENTS: _reject()
            now = self.clock()
            if now.tzinfo is None or now.utcoffset() is None: _reject()
            event = AuditEvent(len(events)+1, '1.0', event_type, correlation_id, fields,
                               now, events[-1].event_hash if events else None, '')
            self._transition(events, event)
            event = replace(event, event_hash=_hash(event))
            self._publish(f'{event.sequence:020d}.json', _bytes(event), replace_existing=False)
            self._publish('HEAD', f'{event.sequence} {event.event_hash}\n'.encode('ascii'), replace_existing=True)

    def _publish(self, name, content, *, replace_existing):
        pending = name + '.' + uuid.uuid4().hex + '.pending'
        fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=self.fd)
        try:
            os.fchmod(fd, 0o600)
            data = memoryview(content)
            while data:
                count = os.write(fd, data)
                if count <= 0: raise OSError('short audit write')
                data = data[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        if replace_existing:
            os.replace(pending, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
        else:
            os.link(pending, name, src_dir_fd=self.fd, dst_dir_fd=self.fd, follow_symlinks=False)
            os.unlink(pending, dir_fd=self.fd)
        os.fsync(self.fd)
