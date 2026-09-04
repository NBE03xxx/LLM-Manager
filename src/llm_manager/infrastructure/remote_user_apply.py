from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import utc_now
from llm_manager.domain.serialization import to_primitive

from .backup import MAX_ITEM_BYTES, _atomic_write, _within


REMOTE_USER_APPLY_PROTOCOL_VERSION = 1
REMOTE_USER_APPLY_OPERATION = "apply_opencode_user_config"
MAX_REMOTE_USER_APPLY_REQUEST_BYTES = 64 * 1024
MAX_REMOTE_USER_APPLY_LIFETIME = timedelta(minutes=10)
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_ALLOWED_TARGETS = frozenset(
    {
        ".config/opencode/opencode.jsonc",
        ".config/opencode/opencode.json",
        ".config/opencode/config.json",
    }
)


@dataclass(frozen=True, slots=True)
class RemoteUserApplyRequest:
    protocol_version: int
    operation: str
    request_id: str
    plan_id: str
    change_set_hash: str
    backup_id: str
    local_manifest_hash: str
    host_id: str
    host_fingerprint: str
    target: str
    before_hash: str | None
    after_hash: str
    requested_at: datetime
    expires_at: datetime
    request_hash: str = ""

    def with_hash(self) -> "RemoteUserApplyRequest":
        unhashed = replace(self, request_hash="")
        return replace(unhashed, request_hash=hashlib.sha256(_request_bytes(unhashed)).hexdigest())


@dataclass(frozen=True, slots=True)
class RemoteUserApplyResult:
    request_id: str
    request_hash: str
    host_id: str
    host_fingerprint: str
    target: str
    before_hash: str | None
    after_hash: str


class RemoteUserApplyExecutor:
    """Unprivileged executor for one hash-bound OpenCode config replacement."""

    def __init__(self, staging_root: Path, home: Path, owner_uid: int, *, clock=utc_now) -> None:
        self.staging_root = staging_root.absolute()
        self.home = home.absolute()
        self.owner_uid = owner_uid
        self.clock = clock

    def execute(
        self, request_id: str, request_hash: str, cancellation: CancellationToken
    ) -> bytes:
        if not _IDENTIFIER.fullmatch(request_id) or not _DIGEST.fullmatch(request_hash):
            raise AdapterError("invalid_remote_user_apply_invocation", "apply identity is invalid")
        if cancellation.cancelled:
            raise OperationCancelled("remote user apply cancelled")
        directory = self.staging_root / request_id / request_hash
        self._private_directory(self.staging_root)
        self._private_directory(directory.parent)
        self._private_directory(directory)
        if not _within(directory.resolve(), self.staging_root.resolve()):
            raise AdapterError("unsafe_remote_staging", "apply staging escaped its root")
        request = decode_remote_user_apply_request(
            self._private_file(directory / "request.json", MAX_REMOTE_USER_APPLY_REQUEST_BYTES),
            expected_hash=request_hash,
            now=self.clock(),
        )
        if request.request_id != request_id:
            raise AdapterError("remote_user_apply_binding_mismatch", "request identity changed")
        payload_path = directory / "items" / f"0000-{request.after_hash}.bin"
        payload = self._private_file(payload_path, MAX_ITEM_BYTES)
        if hashlib.sha256(payload).hexdigest() != request.after_hash:
            raise AdapterError("remote_user_apply_payload_mismatch", "payload hash changed")
        items = directory / "items"
        if {path.name for path in items.iterdir()} != {payload_path.name}:
            raise AdapterError("remote_user_apply_payload_mismatch", "staged payload set is unexpected")
        target = self._target(request.target)
        actual_before = self._current_hash(target)
        if actual_before != request.before_hash:
            raise AdapterError("stale_plan", "remote target changed after planning")
        result_path = directory / "result.json"
        if result_path.exists() or result_path.is_symlink():
            raise AdapterError("remote_result_exists", "remote apply result is immutable")
        mode = (target.stat().st_mode & 0o7777) if target.exists() else 0o600
        _atomic_write(target, payload, mode)
        actual_after = self._current_hash(target)
        if actual_after != request.after_hash:
            raise AdapterError("remote_user_apply_verification_failed", "written target hash differs")
        result = RemoteUserApplyResult(
            request.request_id, request.request_hash, request.host_id,
            request.host_fingerprint, request.target, request.before_hash, actual_after,
        )
        content = _canonical(result)
        _atomic_write(result_path, content, 0o600)
        return content

    def _target(self, relative: str) -> Path:
        if relative not in _ALLOWED_TARGETS:
            raise AdapterError("remote_user_apply_target_not_allowed", "target is not an OpenCode user config")
        if self.home == Path("/") or self.home.is_symlink() or not self.home.is_dir():
            raise AdapterError("unsafe_remote_home", "remote user home is unsafe")
        target = self.home / Path(PurePosixPath(relative).as_posix())
        if target.is_symlink() or not _within(target.parent.resolve(), self.home.resolve()):
            raise AdapterError("unsafe_remote_user_apply_target", "target escaped remote user home")
        if target.exists():
            metadata = target.stat(follow_symlinks=False)
            if not target.is_file() or metadata.st_uid != self.owner_uid:
                raise AdapterError("unsafe_remote_user_apply_target", "target type or owner is unsafe")
        elif not target.parent.is_dir() or target.parent.is_symlink():
            raise AdapterError("unsafe_remote_user_apply_target", "target parent is missing or unsafe")
        return target

    @staticmethod
    def _current_hash(target: Path) -> str | None:
        return hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None

    def _private_directory(self, path: Path) -> None:
        if path.is_symlink() or not path.is_dir():
            raise AdapterError("unsafe_remote_staging", "staging directory is missing or unsafe")
        metadata = path.stat(follow_symlinks=False)
        if metadata.st_uid != self.owner_uid or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise AdapterError("unsafe_remote_staging", "staging directory owner or mode is unsafe")

    def _private_file(self, path: Path, max_bytes: int) -> bytes:
        if path.is_symlink() or not path.is_file():
            raise AdapterError("unsafe_remote_staging", "staged file is missing or unsafe")
        metadata = path.stat(follow_symlinks=False)
        if metadata.st_uid != self.owner_uid or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_size > max_bytes:
            raise AdapterError("unsafe_remote_staging", "staged file owner, mode, or size is unsafe")
        return path.read_bytes()


def encode_remote_user_apply_request(request: RemoteUserApplyRequest) -> bytes:
    validate_remote_user_apply_request(request, request.request_hash, now=request.requested_at)
    content = _request_bytes(request)
    if len(content) > MAX_REMOTE_USER_APPLY_REQUEST_BYTES:
        raise AdapterError("remote_user_apply_request_too_large", "apply request exceeds its bound")
    return content


def decode_remote_user_apply_request(
    content: bytes, *, expected_hash: str, now: datetime
) -> RemoteUserApplyRequest:
    if len(content) > MAX_REMOTE_USER_APPLY_REQUEST_BYTES:
        raise AdapterError("remote_user_apply_request_too_large", "apply request exceeds its bound")
    try:
        value = json.loads(content.decode("utf-8"))
        request = _decode_request(value)
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise AdapterError("invalid_remote_user_apply_request", "apply request is malformed") from error
    if content != _request_bytes(request):
        raise AdapterError("invalid_remote_user_apply_request", "apply request is not canonical")
    validate_remote_user_apply_request(request, expected_hash, now=now)
    return request


def validate_remote_user_apply_request(
    request: RemoteUserApplyRequest, expected_hash: str, *, now: datetime
) -> None:
    if request.protocol_version != REMOTE_USER_APPLY_PROTOCOL_VERSION or request.operation != REMOTE_USER_APPLY_OPERATION:
        raise AdapterError("remote_user_apply_operation_not_allowed", "apply protocol or operation is not allowlisted")
    for value in (request.request_id, request.plan_id, request.backup_id, request.host_id):
        if not _IDENTIFIER.fullmatch(value):
            raise AdapterError("invalid_remote_user_apply_identifier", "apply identifier is invalid")
    for digest in (request.change_set_hash, request.local_manifest_hash, request.after_hash, request.request_hash, expected_hash):
        if not _DIGEST.fullmatch(digest):
            raise AdapterError("invalid_remote_user_apply_hash", "apply hash is invalid")
    if request.before_hash is not None and not _DIGEST.fullmatch(request.before_hash):
        raise AdapterError("invalid_remote_user_apply_hash", "before hash is invalid")
    if not request.host_fingerprint or request.target not in _ALLOWED_TARGETS:
        raise AdapterError("invalid_remote_user_apply_binding", "host fingerprint and fixed target are required")
    expected = hashlib.sha256(_request_bytes(replace(request, request_hash=""))).hexdigest()
    if request.request_hash != expected_hash or request.request_hash != expected:
        raise AdapterError("remote_user_apply_request_hash_mismatch", "apply request integrity check failed")
    if request.requested_at.tzinfo is None or request.expires_at.tzinfo is None:
        raise AdapterError("invalid_remote_user_apply_expiry", "apply timestamps require timezone")
    lifetime = request.expires_at - request.requested_at
    if lifetime <= timedelta(0) or lifetime > MAX_REMOTE_USER_APPLY_LIFETIME or now < request.requested_at or now >= request.expires_at:
        raise AdapterError("expired_remote_user_apply_request", "apply request is outside its validity window")


def _request_bytes(request: RemoteUserApplyRequest) -> bytes:
    return _canonical(request)


def _canonical(value: object) -> bytes:
    return json.dumps(to_primitive(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode_request(value: object) -> RemoteUserApplyRequest:
    fields = {
        "protocol_version", "operation", "request_id", "plan_id", "change_set_hash",
        "backup_id", "local_manifest_hash", "host_id", "host_fingerprint", "target",
        "before_hash", "after_hash", "requested_at", "expires_at", "request_hash",
    }
    if not isinstance(value, dict) or set(value) != fields or type(value["protocol_version"]) is not int:
        raise ValueError("invalid request fields")
    strings = fields - {"protocol_version", "before_hash"}
    if any(not isinstance(value[key], str) for key in strings) or (
        value["before_hash"] is not None and not isinstance(value["before_hash"], str)
    ):
        raise ValueError("invalid request values")
    return RemoteUserApplyRequest(
        value["protocol_version"], value["operation"], value["request_id"], value["plan_id"],
        value["change_set_hash"], value["backup_id"], value["local_manifest_hash"],
        value["host_id"], value["host_fingerprint"], value["target"], value["before_hash"],
        value["after_hash"], datetime.fromisoformat(value["requested_at"]),
        datetime.fromisoformat(value["expires_at"]), value["request_hash"],
    )
