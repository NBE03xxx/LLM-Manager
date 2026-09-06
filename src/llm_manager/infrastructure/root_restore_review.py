"""Privileged restore review producer, for a future dedicated PolicyKit entry.

The existing Apply action must not dispatch here. Hash comparison is not
PolicyKit authentication; production callers must use resolve_restore_caller.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import utc_now
from llm_manager.domain.serialization import to_primitive
from .local_root_restore_preflight import RootRestoreReviewEvidence
from .local_root_restore_protocol import LocalRootRestoreRequest, RootRestoreFileState, PROTOCOL, decode_request
from .root_backup_capture import decrypt_root_backup
from .root_backup_evidence import _cancel, _ID


@dataclass(frozen=True, slots=True)
class RestoreCaller:
    uid: int
    host_id: str


def resolve_restore_caller() -> RestoreCaller:
    if os.geteuid() != 0:
        _reject('root_required')
    text = os.environ.get('PKEXEC_UID', '')
    if not re.fullmatch(r'[1-9][0-9]{0,9}', text) or not 0 < int(text) < 2**32 - 1:
        _reject('invalid_restore_caller')
    host = 'local:' + os.uname().nodename
    if not _ID.fullmatch(host): _reject('invalid_restore_host')
    return RestoreCaller(int(text), host)


@dataclass(frozen=True, slots=True)
class RootRestoreSelection:
    host_id: str
    caller_uid: int
    backup_id: str
    manifest_hash: str
    origin_record_hash: str
    source_apply_request_hash: str
    inventory_hash: str
    target: str
    current: RootRestoreFileState
    backup: RootRestoreFileState
    created_at: datetime
    expires_at: datetime

    @property
    def preview_hash(self) -> str:
        return _hash(self)

    def request(self, request_id: str, approval_id: str) -> LocalRootRestoreRequest:
        return LocalRootRestoreRequest(
            PROTOCOL, 1, request_id, self.host_id, self.caller_uid, self.backup_id,
            self.manifest_hash, self.inventory_hash, self.preview_hash, approval_id,
            self.target, self.current, self.backup, self.created_at, self.expires_at,
        ).with_hash()


class ProduceRootRestoreReview:
    def __init__(self, origins, cipher, target, store, *,
                 identity: Callable[[], RestoreCaller] = resolve_restore_caller,
                 clock: Callable[[], datetime] = utc_now):
        self.origins, self.cipher, self.target, self.store = origins, cipher, target, store
        self.identity, self.clock = identity, clock

    def preview(self, backup_id: str, cancellation: CancellationToken) -> RootRestoreSelection:
        caller = self.identity()
        with self.target.locked(cancellation):
            return self._selection(backup_id, caller, self.clock(), cancellation)

    def approve(self, content: bytes, expected_hash: str, cancellation: CancellationToken) -> RootRestoreReviewEvidence:
        caller = self.identity()
        _cancel(cancellation)
        intent = decode_request(content, expected_hash=expected_hash, expected_caller_uid=caller.uid,
                                expected_host_id=caller.host_id, now=self.clock())
        with self.target.locked(cancellation):
            selection = self._selection(intent.backup_id, caller, intent.requested_at, cancellation)
            if selection.request(intent.request_id, intent.approval_id) != intent:
                _reject('root_restore_review_changed')
            now = self.clock()
            if not intent.requested_at <= now < selection.expires_at:
                _reject('expired_root_restore_review')
            review = RootRestoreReviewEvidence(intent, now, selection.expires_at,
                                               selection.origin_record_hash, selection.source_apply_request_hash)
            _cancel(cancellation)
            self.store.save_review(review, cancellation)
            return review

    def _selection(self, backup_id, caller, created_at, cancellation):
        _cancel(cancellation)
        record, envelope = self.origins.inspect(backup_id, cancellation)
        if record.host_id != caller.host_id:
            _reject('root_restore_origin_host_mismatch')
        current = self.target.observe_target(record.target, cancellation)
        if record.original.exists:
            decrypt_root_backup(record, envelope, self.cipher)
        if self.origins.read(backup_id, record.record_hash, cancellation) != (record, envelope):
            _reject('root_restore_origin_changed')
        if self.target.observe_target(record.target, cancellation) != current:
            _reject('root_restore_target_changed')
        _cancel(cancellation)
        if current == record.original: _reject('root_restore_no_change')
        # A selected-origin snapshot, not an inventory of all host backups.
        inventory = _hash({'scope': 'root_restore_selected_origin/1', 'host_id': caller.host_id,
                           'backup_id': backup_id, 'origin_record_hash': record.record_hash})
        return RootRestoreSelection(caller.host_id, caller.uid, backup_id, record.source_manifest_hash,
                                    record.record_hash, record.source_apply_request_hash, inventory,
                                    record.target, current, record.original, created_at, created_at + timedelta(minutes=5))


def _hash(value):
    return hashlib.sha256(json.dumps(to_primitive(value), ensure_ascii=False, sort_keys=True,
                                   separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _reject(code):
    raise AdapterError(code, 'root restore review rejected')
