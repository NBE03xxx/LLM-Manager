from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import utc_now
from llm_manager.domain.serialization import to_primitive

from .backup import MAX_ITEM_BYTES, _atomic_write, _fsync_directory, _within


REMOTE_USER_ROLLBACK_PROTOCOL_VERSION = 1
REMOTE_USER_ROLLBACK_OPERATION = "rollback_opencode_user_config"
MAX_REMOTE_USER_ROLLBACK_REQUEST_BYTES = 64 * 1024
_LIFETIME = timedelta(minutes=10)
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_TARGETS = frozenset(
    {
        ".config/opencode/opencode.jsonc",
        ".config/opencode/opencode.json",
        ".config/opencode/config.json",
    }
)


@dataclass(frozen=True, slots=True)
class RemoteUserRollbackRequest:
    protocol_version: int
    operation: str
    request_id: str
    apply_request_hash: str
    plan_id: str
    change_set_hash: str
    backup_id: str
    local_manifest_hash: str
    host_id: str
    host_fingerprint: str
    target: str
    expected_current_hash: str
    restore_existed: bool
    restore_hash: str | None
    restore_mode: int | None
    requested_at: datetime
    expires_at: datetime
    request_hash: str = ""

    def with_hash(self) -> "RemoteUserRollbackRequest":
        value = replace(self, request_hash="")
        return replace(value, request_hash=hashlib.sha256(_canonical(value)).hexdigest())


@dataclass(frozen=True, slots=True)
class RemoteUserRollbackResult:
    request_id: str
    request_hash: str
    apply_request_hash: str
    host_id: str
    host_fingerprint: str
    target: str
    restored_hash: str | None


class RemoteUserRollbackExecutor:
    """Unprivileged, single-target rollback bound to one completed Apply."""

    def __init__(self, staging_root: Path, home: Path, owner_uid: int, *, clock=utc_now) -> None:
        self.staging_root = staging_root.absolute()
        self.home = home.absolute()
        self.owner_uid = owner_uid
        self.clock = clock

    def execute(
        self, request_id: str, request_hash: str, cancellation: CancellationToken
    ) -> bytes:
        _identity(request_id, request_hash)
        _cancel(cancellation)
        directory = self.staging_root / request_id / request_hash
        for path in (self.staging_root, directory.parent, directory, directory / "items"):
            self._private_directory(path)
        if not _within(directory.resolve(), self.staging_root.resolve()):
            raise AdapterError("unsafe_remote_staging", "rollback staging escaped its root")
        request = decode_remote_user_rollback_request(
            self._private_file(directory / "request.json", MAX_REMOTE_USER_ROLLBACK_REQUEST_BYTES),
            expected_hash=request_hash,
            now=self.clock(),
        )
        if request.request_id != request_id:
            raise AdapterError("remote_user_rollback_binding_mismatch", "rollback identity changed")
        items = directory / "items"
        expected_names = (
            {f"0000-{request.restore_hash}.bin"} if request.restore_existed else set()
        )
        if {path.name for path in items.iterdir()} != expected_names:
            raise AdapterError("remote_user_rollback_payload_mismatch", "rollback payload set is unexpected")
        restore_content = None
        if request.restore_existed:
            assert request.restore_hash is not None
            restore_content = self._private_file(
                items / f"0000-{request.restore_hash}.bin", MAX_ITEM_BYTES
            )
            if hashlib.sha256(restore_content).hexdigest() != request.restore_hash:
                raise AdapterError("remote_user_rollback_payload_mismatch", "rollback payload hash changed")
        target = self._target(request.target)
        if self._hash(target) != request.expected_current_hash:
            raise AdapterError("stale_rollback_target", "remote target changed after Apply")
        result_path = directory / "result.json"
        if result_path.exists() or result_path.is_symlink():
            raise AdapterError("remote_result_exists", "remote rollback result is immutable")
        _cancel(cancellation)
        if restore_content is not None:
            assert request.restore_mode is not None
            _atomic_write(target, restore_content, request.restore_mode)
        else:
            if not target.exists():
                raise AdapterError("stale_rollback_target", "created target is already absent")
            target.unlink()
            _fsync_directory(target.parent)
        restored_hash = self._hash(target)
        if restored_hash != request.restore_hash:
            raise AdapterError("remote_user_rollback_verification_failed", "restored target hash differs")
        result = RemoteUserRollbackResult(
            request.request_id, request.request_hash, request.apply_request_hash,
            request.host_id, request.host_fingerprint, request.target, restored_hash,
        )
        content = _canonical(result)
        _atomic_write(result_path, content, 0o600)
        return content

    def _target(self, relative: str) -> Path:
        if relative not in _TARGETS or self.home == Path("/") or self.home.is_symlink() or not self.home.is_dir():
            raise AdapterError("remote_user_rollback_target_not_allowed", "rollback target is unsafe")
        target = self.home / relative
        if target.is_symlink() or not _within(target.parent.resolve(), self.home.resolve()):
            raise AdapterError("remote_user_rollback_target_not_allowed", "rollback target escaped home")
        if target.exists() and (not target.is_file() or target.stat(follow_symlinks=False).st_uid != self.owner_uid):
            raise AdapterError("remote_user_rollback_target_not_allowed", "rollback target type or owner is unsafe")
        if not target.parent.is_dir() or target.parent.is_symlink():
            raise AdapterError("remote_user_rollback_target_not_allowed", "rollback target parent is unsafe")
        return target

    @staticmethod
    def _hash(path: Path) -> str | None:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

    def _private_directory(self, path: Path) -> None:
        if path.is_symlink() or not path.is_dir():
            raise AdapterError("unsafe_remote_staging", "rollback staging directory is unsafe")
        metadata = path.stat(follow_symlinks=False)
        if metadata.st_uid != self.owner_uid or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise AdapterError("unsafe_remote_staging", "rollback staging metadata is unsafe")

    def _private_file(self, path: Path, maximum: int) -> bytes:
        if path.is_symlink() or not path.is_file():
            raise AdapterError("unsafe_remote_staging", "rollback staged file is unsafe")
        metadata = path.stat(follow_symlinks=False)
        if metadata.st_uid != self.owner_uid or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_size > maximum:
            raise AdapterError("unsafe_remote_staging", "rollback staged file metadata is unsafe")
        return path.read_bytes()


def encode_remote_user_rollback_request(request: RemoteUserRollbackRequest) -> bytes:
    validate_remote_user_rollback_request(request, request.request_hash, now=request.requested_at)
    content = _canonical(request)
    if len(content) > MAX_REMOTE_USER_ROLLBACK_REQUEST_BYTES:
        raise AdapterError("remote_user_rollback_request_too_large", "rollback request exceeds its bound")
    return content


def decode_remote_user_rollback_request(
    content: bytes, *, expected_hash: str, now: datetime
) -> RemoteUserRollbackRequest:
    if len(content) > MAX_REMOTE_USER_ROLLBACK_REQUEST_BYTES:
        raise AdapterError("remote_user_rollback_request_too_large", "rollback request exceeds its bound")
    try:
        value = json.loads(content.decode("utf-8"))
        request = _decode_request(value)
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise AdapterError("invalid_remote_user_rollback_request", "rollback request is malformed") from error
    if content != _canonical(request):
        raise AdapterError("invalid_remote_user_rollback_request", "rollback request is not canonical")
    validate_remote_user_rollback_request(request, expected_hash, now=now)
    return request


def validate_remote_user_rollback_request(
    request: RemoteUserRollbackRequest, expected_hash: str, *, now: datetime
) -> None:
    if request.protocol_version != REMOTE_USER_ROLLBACK_PROTOCOL_VERSION or request.operation != REMOTE_USER_ROLLBACK_OPERATION:
        raise AdapterError("remote_user_rollback_operation_not_allowed", "rollback operation is not allowlisted")
    for value in (request.request_id, request.plan_id, request.backup_id, request.host_id):
        if not _IDENTIFIER.fullmatch(value):
            raise AdapterError("invalid_remote_user_rollback_identifier", "rollback identifier is invalid")
    for digest in (
        request.apply_request_hash, request.change_set_hash, request.local_manifest_hash,
        request.expected_current_hash, request.request_hash, expected_hash,
    ):
        if not _DIGEST.fullmatch(digest):
            raise AdapterError("invalid_remote_user_rollback_hash", "rollback hash is invalid")
    if request.restore_hash is not None and not _DIGEST.fullmatch(request.restore_hash):
        raise AdapterError("invalid_remote_user_rollback_hash", "restore hash is invalid")
    if (
        request.restore_existed != (request.restore_hash is not None)
        or request.restore_existed != (request.restore_mode is not None)
        or (request.restore_mode is not None and not 0 <= request.restore_mode <= 0o7777)
        or request.target not in _TARGETS
        or not request.host_fingerprint
    ):
        raise AdapterError("invalid_remote_user_rollback_binding", "rollback binding is invalid")
    expected = hashlib.sha256(_canonical(replace(request, request_hash=""))).hexdigest()
    if request.request_hash != expected_hash or request.request_hash != expected:
        raise AdapterError("remote_user_rollback_request_hash_mismatch", "rollback request integrity failed")
    if request.requested_at.tzinfo is None or request.expires_at.tzinfo is None:
        raise AdapterError("invalid_remote_user_rollback_expiry", "rollback timestamps require timezone")
    lifetime = request.expires_at - request.requested_at
    if lifetime <= timedelta(0) or lifetime > _LIFETIME or now < request.requested_at or now >= request.expires_at:
        raise AdapterError("expired_remote_user_rollback_request", "rollback request is outside its validity window")


def decode_remote_user_rollback_result(content: bytes) -> RemoteUserRollbackResult:
    fields = {"request_id", "request_hash", "apply_request_hash", "host_id", "host_fingerprint", "target", "restored_hash"}
    try:
        value = json.loads(content.decode("utf-8"))
        if not isinstance(value, dict) or set(value) != fields:
            raise ValueError("invalid result fields")
        result = RemoteUserRollbackResult(**value)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise AdapterError("invalid_remote_user_rollback_result", "rollback result is malformed") from error
    if content != _canonical(result):
        raise AdapterError("invalid_remote_user_rollback_result", "rollback result is not canonical")
    _identity(result.request_id, result.request_hash)
    if not _DIGEST.fullmatch(result.apply_request_hash) or result.target not in _TARGETS:
        raise AdapterError("invalid_remote_user_rollback_result", "rollback result binding is invalid")
    if result.restored_hash is not None and not _DIGEST.fullmatch(result.restored_hash):
        raise AdapterError("invalid_remote_user_rollback_result", "restored hash is invalid")
    return result


def validate_remote_user_rollback_result(
    request: RemoteUserRollbackRequest, result: RemoteUserRollbackResult
) -> None:
    if (
        result.request_id, result.request_hash, result.apply_request_hash, result.host_id,
        result.host_fingerprint, result.target, result.restored_hash,
    ) != (
        request.request_id, request.request_hash, request.apply_request_hash, request.host_id,
        request.host_fingerprint, request.target, request.restore_hash,
    ):
        raise AdapterError("remote_user_rollback_result_binding_mismatch", "rollback result does not match request")


def _decode_request(value: object) -> RemoteUserRollbackRequest:
    fields = {
        "protocol_version", "operation", "request_id", "apply_request_hash", "plan_id",
        "change_set_hash", "backup_id", "local_manifest_hash", "host_id", "host_fingerprint",
        "target", "expected_current_hash", "restore_existed", "restore_hash", "restore_mode", "requested_at",
        "expires_at", "request_hash",
    }
    if not isinstance(value, dict) or set(value) != fields or type(value["protocol_version"]) is not int or type(value["restore_existed"]) is not bool:
        raise ValueError("invalid request fields")
    string_fields = fields - {"protocol_version", "restore_existed", "restore_hash", "restore_mode"}
    if (
        any(not isinstance(value[key], str) for key in string_fields)
        or (value["restore_hash"] is not None and not isinstance(value["restore_hash"], str))
        or (value["restore_mode"] is not None and type(value["restore_mode"]) is not int)
    ):
        raise ValueError("invalid request values")
    return RemoteUserRollbackRequest(
        value["protocol_version"], value["operation"], value["request_id"],
        value["apply_request_hash"], value["plan_id"], value["change_set_hash"],
        value["backup_id"], value["local_manifest_hash"], value["host_id"],
        value["host_fingerprint"], value["target"], value["expected_current_hash"],
        value["restore_existed"], value["restore_hash"], value["restore_mode"],
        datetime.fromisoformat(value["requested_at"]), datetime.fromisoformat(value["expires_at"]),
        value["request_hash"],
    )


def _identity(request_id: str, request_hash: str) -> None:
    if not _IDENTIFIER.fullmatch(request_id) or not _DIGEST.fullmatch(request_hash):
        raise AdapterError("invalid_remote_user_rollback_invocation", "rollback identity is invalid")


def _canonical(value: object) -> bytes:
    return json.dumps(to_primitive(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _cancel(cancellation: CancellationToken) -> None:
    if cancellation.cancelled:
        raise OperationCancelled("remote user rollback cancelled")
