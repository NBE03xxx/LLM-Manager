"""Local root manual-restore intent codec; no authority, I/O, or dispatch.

A valid digest only binds bytes. A future privileged executor must independently
verify PolicyKit identity, trusted inventory/preview evidence, current target,
backup contents and immutable attempt state before any mutation.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from llm_manager.application.errors import AdapterError
from llm_manager.domain.serialization import to_primitive
from llm_manager.planning.ollama import DROP_IN_PATH

PROTOCOL = "llm-manager.local-root-manual-restore"
PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 16 * 1024
MAX_REQUEST_LIFETIME = timedelta(minutes=5)
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class RootRestoreFileState:
    exists: bool
    sha256: str | None = None
    mode: int | None = None
    uid: int | None = None
    gid: int | None = None


@dataclass(frozen=True, slots=True)
class LocalRootRestoreRequest:
    protocol: str
    protocol_version: int
    request_id: str
    host_id: str
    caller_uid: int
    backup_id: str
    manifest_hash: str
    inventory_hash: str
    preview_hash: str
    approval_id: str
    target: str
    current: RootRestoreFileState
    backup: RootRestoreFileState
    requested_at: datetime
    expires_at: datetime
    request_hash: str = ""

    def with_hash(self) -> "LocalRootRestoreRequest":
        value = replace(self, request_hash="")
        return replace(value, request_hash=hashlib.sha256(_canonical(value)).hexdigest())


def encode_request(request: LocalRootRestoreRequest) -> bytes:
    """Validate the intent's shape, not the caller's authorization."""
    validate_request(
        request, expected_hash=request.request_hash,
        expected_caller_uid=request.caller_uid, expected_host_id=request.host_id,
        now=request.requested_at,
    )
    content = _canonical(request)
    if len(content) > MAX_REQUEST_BYTES:
        _reject("root_restore_request_too_large")
    return content


def decode_request(
    content: bytes, *, expected_hash: str, expected_caller_uid: int,
    expected_host_id: str, now: datetime,
) -> LocalRootRestoreRequest:
    if len(content) > MAX_REQUEST_BYTES:
        _reject("root_restore_request_too_large")
    try:
        value = json.loads(content.decode("utf-8"))
        value["current"] = RootRestoreFileState(**value["current"])
        value["backup"] = RootRestoreFileState(**value["backup"])
        value["requested_at"] = datetime.fromisoformat(value["requested_at"])
        value["expires_at"] = datetime.fromisoformat(value["expires_at"])
        request = LocalRootRestoreRequest(**value)
        canonical = _canonical(request)
    except (UnicodeError, ValueError, TypeError, KeyError, RecursionError) as error:
        raise AdapterError("invalid_root_restore_request", "invalid root restore request") from error
    if canonical != content:
        _reject("noncanonical_root_restore_request")
    validate_request(
        request, expected_hash=expected_hash, expected_caller_uid=expected_caller_uid,
        expected_host_id=expected_host_id, now=now,
    )
    return request


def validate_request(
    request: LocalRootRestoreRequest, *, expected_hash: str,
    expected_caller_uid: int, expected_host_id: str, now: datetime,
) -> None:
    if request.protocol != PROTOCOL or type(request.protocol_version) is not int or request.protocol_version != PROTOCOL_VERSION:
        _reject("unsupported_root_restore_protocol")
    for value in (request.request_id, request.host_id, request.backup_id, request.approval_id):
        if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
            _reject("invalid_root_restore_identity")
    if (
        type(request.caller_uid) is not int
        or not 0 < request.caller_uid < 2**32 - 1
        or type(expected_caller_uid) is not int
        or request.caller_uid != expected_caller_uid
        or request.host_id != expected_host_id
    ):
        _reject("root_restore_caller_mismatch")
    if request.target != DROP_IN_PATH:
        _reject("root_restore_target_not_allowed")
    for value in (request.manifest_hash, request.inventory_hash, request.preview_hash, request.request_hash, expected_hash):
        if not isinstance(value, str) or not _DIGEST.fullmatch(value):
            _reject("invalid_root_restore_digest")
    if request.request_hash != expected_hash or request.with_hash() != request:
        _reject("root_restore_hash_mismatch")
    for value in (request.requested_at, request.expires_at, now):
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            _reject("invalid_root_restore_expiry")
    lifetime = request.expires_at - request.requested_at
    if not timedelta(0) < lifetime <= MAX_REQUEST_LIFETIME or not request.requested_at <= now < request.expires_at:
        _reject("expired_root_restore_request")
    _validate_file_state(request.current)
    _validate_file_state(request.backup)
    if request.current == request.backup:
        _reject("root_restore_no_change")


def _validate_file_state(state: RootRestoreFileState) -> None:
    if not isinstance(state, RootRestoreFileState) or type(state.exists) is not bool:
        _reject("invalid_root_restore_file_state")
    metadata = (state.sha256, state.mode, state.uid, state.gid)
    if not state.exists:
        if any(value is not None for value in metadata):
            _reject("invalid_root_restore_file_state")
        return
    if (
        not isinstance(state.sha256, str) or not _DIGEST.fullmatch(state.sha256)
        or type(state.mode) is not int or state.mode != 0o644
        or type(state.uid) is not int or state.uid != 0
        or type(state.gid) is not int or state.gid != 0
    ):
        _reject("invalid_root_restore_file_state")


def _canonical(value: object) -> bytes:
    return json.dumps(to_primitive(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _reject(code: str) -> None:
    raise AdapterError(code, "local root restore request rejected")
