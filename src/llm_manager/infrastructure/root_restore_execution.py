"""Dedicated single-target root restore coordinator; no production dispatch."""
from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime
from typing import Protocol

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import utc_now
from llm_manager.planning.ollama import DROP_IN_PATH
from .local_root_restore_preflight import CheckLocalRootRestore, _same_state, _validate_review
from .local_root_restore_protocol import LocalRootRestoreRequest, RootRestoreFileState, validate_request, _validate_file_state
from .backup_crypto import MAX_PLAINTEXT_BYTES
from .root_backup_capture import observe_root_target, decrypt_root_backup
from .root_backup_evidence import RootBackupEvidenceReader, _cancel, _open_fixed_directory
from .root_backup_verification import VerifyRootBackupOrigin
from .root_restore_store import RootRestoreStore, RootRestoreState
from .root_target_lock import locked_root_target


class RootRestoreAudit(Protocol):
    def append(self, event_type: str, correlation_id: str, fields: tuple[tuple[str, object], ...]) -> None: ...


class RootRestoreService(Protocol):
    def reload_restart_validate(self, restored_content: bytes | None, cancellation: CancellationToken) -> bool: ...


class RootRestorePersistenceError(AdapterError):
    def __init__(self, request_hash: str, state: RootRestoreState):
        super().__init__('root_restore_result_not_persisted', 'restore result requires reconciliation')
        self.request_hash, self.state = request_hash, state


def open_production_source_parent() -> int:
    return _open_fixed_directory(DROP_IN_PATH.rsplit('/', 1)[0], private=False)


class SingleRootRestoreTarget:
    """Borrow the securely anchored, fixed drop-in parent FD.

    Explicit owner overrides are for sandbox only. The production caller must
    anchor this FD without following symlinks and coordinate other mutators.
    """
    def __init__(self, parent_fd: int, *, owner_uid: int = 0, owner_gid: int = 0):
        self.fd = parent_fd
        self.owner_uid, self.owner_gid = owner_uid, owner_gid

    def _snapshot(self, cancellation):
        return observe_root_target(self.fd, self.owner_uid, self.owner_gid, cancellation)

    def observe_target(self, target, cancellation):
        if target != DROP_IN_PATH: _reject('root_restore_target_not_allowed')
        return self._snapshot(cancellation)[0]

    @contextmanager
    def locked(self, cancellation):
        _cancel(cancellation)
        self._snapshot(cancellation)
        with locked_root_target(self.fd):
            _cancel(cancellation)
            yield

    def restore(self, current: RootRestoreFileState, backup: RootRestoreFileState,
                plaintext: bytes | None, cancellation: CancellationToken, *, before_commit: Callable[[], None]):
        _validate_file_state(current)
        _validate_file_state(backup)
        snapshot = self._snapshot(cancellation)
        if not _same_state(snapshot[0], current): _reject('stale_root_restore_target')
        name = DROP_IN_PATH.rsplit('/', 1)[1]
        if not backup.exists:
            if plaintext is not None or not current.exists: _reject('invalid_root_restore_content')
            if self._snapshot(cancellation) != snapshot: _reject('stale_root_restore_target')
            before_commit()
            os.unlink(name, dir_fd=self.fd)
            os.fsync(self.fd)
            return
        if not isinstance(plaintext, bytes) or len(plaintext) > MAX_PLAINTEXT_BYTES or hashlib.sha256(plaintext).hexdigest() != backup.sha256:
            _reject('invalid_root_restore_content')
        temporary = '.llm-restore-' + uuid.uuid4().hex + '.pending'
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=self.fd)
        try:
            data = memoryview(plaintext)
            while data:
                _cancel(cancellation)
                count = os.write(fd, data[:65536])
                if count <= 0: raise OSError('short restore write')
                data = data[count:]
            os.fchmod(fd, 0o644)
            os.fsync(fd)
        finally: os.close(fd)
        if self._snapshot(cancellation) != snapshot: _reject('stale_root_restore_target')
        before_commit()
        if current.exists:
            os.replace(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
        else:
            os.link(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd, follow_symlinks=False)
            os.unlink(temporary, dir_fd=self.fd)
        os.fsync(self.fd)


class ExecuteLocalRootRestore:
    def __init__(self, store: RootRestoreStore, preflight: CheckLocalRootRestore,
                 origins: RootBackupEvidenceReader, verifier: VerifyRootBackupOrigin,
                 target: SingleRootRestoreTarget, audit: RootRestoreAudit, service: RootRestoreService,
                 *, clock: Callable[[], datetime] = utc_now):
        self.store, self.preflight, self.origins, self.verifier = store, preflight, origins, verifier
        self.target, self.audit, self.service, self.clock = target, audit, service, clock

    def execute(self, request: LocalRootRestoreRequest, *, expected_hash: str, caller_uid: int,
                host_id: str, cancellation: CancellationToken):
        validate_request(request, expected_hash=expected_hash, expected_caller_uid=caller_uid,
                         expected_host_id=host_id, now=self.clock())
        with self.target.locked(cancellation):
            self.preflight.execute(request, expected_hash=expected_hash, caller_uid=caller_uid,
                                   host_id=host_id, cancellation=cancellation)
            review = self.store.load_review(request.request_id, cancellation)
            self.verifier.execute(review, cancellation)
            record, envelope = self.origins.read(request.backup_id, review.origin_record_hash, cancellation)
            plaintext = (decrypt_root_backup(record, envelope, self.verifier.cipher) if record.original.exists else None)
            attempt = self.store.begin(request, expected_hash=expected_hash, caller_uid=caller_uid,
                                       host_id=host_id, cancellation=cancellation)
            dispatched = False
            phase = 'start_audit'
            state, error_code = RootRestoreState.COMMITTED, None
            try:
                self.audit.append('root_restore.started', request.request_id, (('request_hash', request.request_hash),))
                phase = 'final_check'
                _cancel(cancellation)
                validate_request(request, expected_hash=expected_hash, expected_caller_uid=caller_uid,
                                 expected_host_id=host_id, now=self.clock())
                if self.store.load_review(request.request_id, cancellation) != review:
                    _reject('root_restore_review_changed')
                if self.origins.read(request.backup_id, review.origin_record_hash, cancellation) != (record, envelope):
                    _reject('root_restore_origin_changed')
                if not _same_state(self.target.observe_target(request.target, cancellation), request.current):
                    _reject('stale_root_restore_target')
                phase = 'mutation'
                dispatched = True
                def before_commit():
                    _cancel(cancellation)
                    _validate_review(review, request, self.clock())
                self.target.restore(request.current, request.backup, plaintext, cancellation, before_commit=before_commit)
                phase = 'validation'
                _cancel(cancellation)
                if not _same_state(self.target.observe_target(request.target, cancellation), request.backup):
                    _reject('root_restore_postcondition_failed')
                if self.service.reload_restart_validate(plaintext, cancellation) is not True:
                    state, error_code = RootRestoreState.FAILED, 'service_validation_failed'
                _cancel(cancellation)
                if not _same_state(self.target.observe_target(request.target, cancellation), request.backup):
                    _reject('root_restore_postcondition_failed')
            except Exception:
                state = RootRestoreState.UNKNOWN if dispatched else RootRestoreState.FAILED
                error_code = phase + '_failed'
            try:
                self.audit.append('root_restore.finished', request.request_id,
                                  (('request_hash', request.request_hash), ('state', state.value), ('error_code', error_code)))
            except Exception:
                state = RootRestoreState.UNKNOWN if dispatched else RootRestoreState.FAILED
                error_code = 'terminal_audit_failed'
            # Once an attempt exists, terminal bookkeeping must not be skipped
            # because the original operation was cancelled.
            try:
                return self.store.finish(attempt, state, error_code, CancellationToken())
            except Exception as error:
                raise RootRestorePersistenceError(request.request_hash, state) from error


def _reject(code):
    raise AdapterError(code, 'local root restore execution rejected')
