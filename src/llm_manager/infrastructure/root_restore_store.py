"""Privileged immutable restore records; no CLI, authorization, or mutation.

save_review is only for a future trusted review producer. Making a root-owned
copy of a user review does not establish approval or backup authenticity.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import utc_now
from llm_manager.domain.serialization import to_primitive
from .local_root_restore_preflight import RootRestoreReviewEvidence, _validate_review
from .local_root_restore_protocol import LocalRootRestoreRequest, decode_request, validate_request
from .root_backup_evidence import RootBackupEvidenceReader, _ID, _HASH, _cancel, _open_fixed_directory

STORE_PATH = '/var/lib/llm-manager/local-root-restore/executions'
MAX_RECORD_BYTES = 16 * 1024


class RootRestoreState(StrEnum):
    COMMITTED = 'committed'
    FAILED = 'failed'
    UNKNOWN = 'unknown'


@dataclass(frozen=True, slots=True)
class RootRestoreAttempt:
    request_id: str
    request_hash: str
    review_hash: str
    started_at: datetime


@dataclass(frozen=True, slots=True)
class RootRestoreResult:
    request_id: str
    request_hash: str
    attempt_hash: str
    state: RootRestoreState
    completed_at: datetime
    error_code: str | None


@dataclass(frozen=True, slots=True)
class RootRestoreExecutionView:
    attempt: RootRestoreAttempt | None
    result: RootRestoreResult | None

    @property
    def requires_attention(self) -> bool:
        return self.attempt is not None and (self.result is None or self.result.state is not RootRestoreState.COMMITTED)


def open_production_execution_directory() -> int:
    return _open_fixed_directory(STORE_PATH)


class RootRestoreStore:
    def __init__(self, directory_fd: int, *, owner_uid: int = 0, owner_gid: int = 0,
                 clock: Callable[[], datetime] = utc_now):
        self.fd, self.clock = directory_fd, clock
        self.reader = RootBackupEvidenceReader(directory_fd, owner_uid=owner_uid, owner_gid=owner_gid)

    def save_review(self, review: RootRestoreReviewEvidence, cancellation: CancellationToken) -> None:
        now = self.clock()
        _validate_review(review, review.approved_request, now)
        request_id = review.approved_request.request_id
        with self._lock(request_id, cancellation, write=True) as names:
            if names: _reject('root_restore_review_exists')
            self._publish(request_id, 'review', review, cancellation)

    def load_review(self, request_id: str, cancellation: CancellationToken) -> RootRestoreReviewEvidence:
        with self._lock(request_id, cancellation):
            review = self._review(request_id, cancellation)
            _validate_review(review, review.approved_request, self.clock())
            return review

    def request_is_unused(self, request_id: str, cancellation: CancellationToken) -> bool:
        return self.load_execution(request_id, cancellation).attempt is None

    def load_execution(self, request_id: str, cancellation: CancellationToken) -> RootRestoreExecutionView:
        with self._lock(request_id, cancellation) as names:
            review = self._review(request_id, cancellation)
            return self._execution(request_id, review, names, cancellation)

    def reconcile(self, request_id: str, *, expected_hash: str, caller_uid: int,
                  host_id: str, cancellation: CancellationToken) -> RootRestoreExecutionView:
        """Read history under one shared lock; never reserve or authorize work.

        Identity must come from the privileged caller resolver, not request
        metadata. Expired reviews remain readable as historical evidence.
        """
        if (not isinstance(expected_hash, str) or not _HASH.fullmatch(expected_hash)
                or type(caller_uid) is not int or caller_uid <= 0
                or not isinstance(host_id, str) or not host_id):
            _reject('invalid_root_restore_status_argument')
        with self._lock(request_id, cancellation) as names:
            review = self._review(request_id, cancellation)
            request = review.approved_request
            if (request.request_hash != expected_hash or request.caller_uid != caller_uid
                    or request.host_id != host_id):
                _reject('root_restore_status_binding_mismatch')
            view = self._execution(request_id, review, names, cancellation)
            _cancel(cancellation)
            return view

    def begin(self, request: LocalRootRestoreRequest, *, expected_hash: str,
              caller_uid: int, host_id: str, cancellation: CancellationToken) -> RootRestoreAttempt:
        validate_request(request, expected_hash=expected_hash, expected_caller_uid=caller_uid,
                         expected_host_id=host_id, now=self.clock())
        with self._lock(request.request_id, cancellation, write=True) as names:
            review = self._review(request.request_id, cancellation)
            now = self.clock()
            _validate_review(review, request, now)
            if self._execution(request.request_id, review, names, cancellation).attempt is not None:
                _reject('root_restore_request_already_used')
            attempt = RootRestoreAttempt(request.request_id, request.request_hash, _digest('review', review), now)
            self._publish(request.request_id, 'attempt', attempt, cancellation)
            return attempt

    def finish(self, attempt: RootRestoreAttempt, state: RootRestoreState,
               error_code: str | None, cancellation: CancellationToken) -> RootRestoreResult:
        with self._lock(attempt.request_id, cancellation, write=True) as names:
            review = self._review(attempt.request_id, cancellation)
            view = self._execution(attempt.request_id, review, names, cancellation)
            if view.attempt is None or _wrap('attempt', view.attempt) != _wrap('attempt', attempt) or view.result is not None:
                _reject('root_restore_result_conflict')
            result = RootRestoreResult(attempt.request_id, attempt.request_hash, _digest('attempt', attempt),
                                       state, self.clock(), error_code)
            _validate_result(result, attempt)
            self._publish(attempt.request_id, 'result', result, cancellation)
            return result

    @contextmanager
    def _lock(self, request_id: str, cancellation: CancellationToken, *, write: bool = False):
        if not isinstance(request_id, str) or not _ID.fullmatch(request_id): _reject('invalid_root_restore_id')
        _cancel(cancellation)
        self.reader._directory()
        fd = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=self.fd)
        try:
            try:
                fcntl.flock(fd, (fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            except OSError as error:
                raise AdapterError('root_restore_store_busy', 'root restore store is busy') from error
            entries = os.listdir(self.fd)
            if len(entries) > 10000: _reject('root_restore_store_too_large')
            names = {name for name in entries if name.startswith(request_id + '.')}
            allowed = {request_id + '.' + kind + '.json' for kind in ('review', 'attempt', 'result')}
            if not names <= allowed: _reject('root_restore_store_incomplete')
            _cancel(cancellation)
            yield names
            self.reader._directory()
        except OSError as error:
            raise AdapterError('root_restore_store_incomplete', 'root restore records require reconciliation') from error
        finally:
            os.close(fd)

    def _review(self, request_id: str, cancellation: CancellationToken) -> RootRestoreReviewEvidence:
        raw = self._payload(request_id, 'review', cancellation)
        try:
            intent = raw['approved_request']
            approval_time = datetime.fromisoformat(raw['approved_at'])
            raw['approved_request'] = decode_request(
                _canonical(intent), expected_hash=intent['request_hash'], expected_caller_uid=intent['caller_uid'],
                expected_host_id=intent['host_id'], now=approval_time,
            )
            raw['approved_at'] = approval_time
            raw['expires_at'] = datetime.fromisoformat(raw['expires_at'])
            review = RootRestoreReviewEvidence(**raw)
            _validate_review(review, review.approved_request, approval_time)
        except (ValueError, TypeError, KeyError) as error:
            raise AdapterError('invalid_root_restore_review', 'stored root restore review is invalid') from error
        if review.approved_request.request_id != request_id: _reject('root_restore_record_binding_mismatch')
        self._same_wire(request_id, 'review', review, cancellation)
        return review

    def _execution(self, request_id, review, names, cancellation):
        attempt = result = None
        if request_id + '.attempt.json' in names:
            raw = self._payload(request_id, 'attempt', cancellation)
            try:
                raw['started_at'] = datetime.fromisoformat(raw['started_at'])
                attempt = RootRestoreAttempt(**raw)
                _aware(attempt.started_at)
                if (attempt.request_id != request_id or attempt.request_hash != review.approved_request.request_hash
                    or attempt.review_hash != _digest('review', review)
                    or not review.approved_at <= attempt.started_at < review.expires_at):
                    _reject('root_restore_record_binding_mismatch')
            except (ValueError, TypeError, KeyError) as error:
                raise AdapterError('invalid_root_restore_attempt', 'invalid stored attempt') from error
            self._same_wire(request_id, 'attempt', attempt, cancellation)
        if request_id + '.result.json' in names:
            if attempt is None: _reject('orphan_root_restore_result')
            raw = self._payload(request_id, 'result', cancellation)
            try:
                raw['completed_at'] = datetime.fromisoformat(raw['completed_at'])
                raw['state'] = RootRestoreState(raw['state'])
                result = RootRestoreResult(**raw)
                _validate_result(result, attempt)
            except (ValueError, TypeError, KeyError) as error:
                raise AdapterError('invalid_root_restore_result', 'invalid stored result') from error
            self._same_wire(request_id, 'result', result, cancellation)
        return RootRestoreExecutionView(attempt, result)

    def _payload(self, request_id, kind, cancellation):
        content = self.reader._read_file(request_id + '.' + kind + '.json', MAX_RECORD_BYTES, cancellation)
        try:
            raw = json.loads(content.decode('utf-8'))
            if set(raw) != {'kind', 'payload', 'hash'} or raw['kind'] != kind or _wrap(kind, raw['payload']) != content:
                _reject('invalid_root_restore_record')
            return raw['payload']
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as error:
            raise AdapterError('invalid_root_restore_record', 'invalid stored record') from error

    def _same_wire(self, request_id, kind, value, cancellation):
        if self.reader._read_file(request_id + '.' + kind + '.json', MAX_RECORD_BYTES, cancellation) != _wrap(kind, value):
            _reject('root_restore_record_changed')

    def _publish(self, request_id, kind, value, cancellation):
        content = _wrap(kind, value)
        if len(content) > MAX_RECORD_BYTES: _reject('root_restore_record_too_large')
        name = request_id + '.' + kind + '.json'
        pending = name + '.' + uuid.uuid4().hex + '.pending'
        fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=self.fd)
        try:
            os.fchmod(fd, 0o600)
            data = memoryview(content)
            while data:
                _cancel(cancellation)
                count = os.write(fd, data)
                if count <= 0: raise OSError('short record write')
                data = data[count:]
            os.fsync(fd)
        finally: os.close(fd)
        _cancel(cancellation)
        os.link(pending, name, src_dir_fd=self.fd, dst_dir_fd=self.fd, follow_symlinks=False)
        os.unlink(pending, dir_fd=self.fd)
        os.fsync(self.fd)


def _validate_result(result, attempt):
    _aware(result.completed_at)
    if (result.request_id != attempt.request_id or result.request_hash != attempt.request_hash
        or result.attempt_hash != _digest('attempt', attempt) or result.completed_at < attempt.started_at
        or not isinstance(result.state, RootRestoreState)):
        _reject('root_restore_result_binding_mismatch')
    if result.state is RootRestoreState.COMMITTED:
        if result.error_code is not None: _reject('invalid_root_restore_result')
    elif not isinstance(result.error_code, str) or not re.fullmatch('[a-z][a-z0-9_]{0,63}', result.error_code):
        _reject('invalid_root_restore_result')


def _aware(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        _reject('invalid_root_restore_record_time')


def _canonical(value):
    return json.dumps(to_primitive(value), sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _digest(kind, value):
    return hashlib.sha256(_canonical({'kind': kind, 'payload': value})).hexdigest()


def _wrap(kind, value):
    return _canonical({'kind': kind, 'payload': value, 'hash': _digest(kind, value)})


def _reject(code):
    raise AdapterError(code, 'root restore record rejected')
