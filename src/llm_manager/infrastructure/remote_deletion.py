from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import utc_now
from llm_manager.domain.serialization import to_primitive

from .backup import _atomic_write, _within


REMOTE_DELETION_PROTOCOL_VERSION = 1
REMOTE_DELETION_OPERATION = "delete-recovery-copy"
MAX_REMOTE_DELETION_BYTES = 1024 * 1024
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_FINGERPRINT = re.compile(r"SHA256:[A-Za-z0-9+/]{43}")


class RemoteDeletionOutcome(StrEnum):
    DELETED = "deleted"
    ALREADY_ABSENT = "already_absent"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RemoteDeletionRequest:
    schema_version: str
    protocol_version: int
    operation: str
    request_id: str
    backup_id: str
    host_id: str
    host_fingerprint: str
    manifest_hash: str
    remote_receipt_hash: str
    key_reference: str
    storage_location: str
    item_hashes: tuple[tuple[str, str | None], ...]
    created_at: datetime
    expires_at: datetime
    request_hash: str = ""

    def with_hash(self) -> "RemoteDeletionRequest":
        value = replace(self, request_hash="")
        return replace(value, request_hash=hashlib.sha256(_bytes(value)).hexdigest())


@dataclass(frozen=True, slots=True)
class RemoteDeletionResult:
    schema_version: str
    request_id: str
    request_hash: str
    backup_id: str
    host_id: str
    host_fingerprint: str
    manifest_hash: str
    remote_receipt_hash: str
    key_reference: str
    outcome: RemoteDeletionOutcome
    error_code: str | None
    completed_at: datetime
    result_hash: str = ""

    def with_hash(self) -> "RemoteDeletionResult":
        value = replace(self, result_hash="")
        return replace(value, result_hash=hashlib.sha256(_bytes(value)).hexdigest())


class RemoteDeletionBackend(Protocol):
    def delete_bound(
        self, request: RemoteDeletionRequest, cancellation: CancellationToken
    ) -> None: ...


class RemoteDeletionHelperExecutor:
    def __init__(self, staging_root: Path, backend: RemoteDeletionBackend,
                 invoking_uid: int, *, clock=utc_now) -> None:
        self.staging_root = staging_root.absolute()
        self.backend = backend
        self.invoking_uid = invoking_uid
        self.clock = clock

    def execute(self, request_id: str, request_hash: str,
                cancellation: CancellationToken) -> bytes:
        if not _IDENTIFIER.fullmatch(request_id) or not _DIGEST.fullmatch(request_hash):
            raise AdapterError("invalid_remote_deletion_identity", "deletion identity is invalid")
        directory = self.staging_root / request_id / request_hash
        for path in (self.staging_root, directory.parent, directory):
            self._directory(path)
        if not _within(directory.resolve(), self.staging_root.resolve()):
            raise AdapterError("unsafe_remote_staging", "deletion staging escaped its root")
        request = decode_remote_deletion_request(
            self._file(directory / "request.json"), expected_hash=request_hash,
            now=self.clock(),
        )
        if request.request_id != request_id:
            raise AdapterError("remote_deletion_binding_mismatch", "request identity changed")
        result_path = directory / "result.json"
        if result_path.exists() or result_path.is_symlink():
            raise AdapterError("remote_result_exists", "remote deletion result is immutable")
        try:
            self.backend.delete_bound(request, cancellation)
            outcome, error_code = RemoteDeletionOutcome.DELETED, None
        except OperationCancelled:
            raise
        except AdapterError as error:
            if error.code == "remote_backup_not_found":
                outcome, error_code = RemoteDeletionOutcome.ALREADY_ABSENT, None
            else:
                outcome, error_code = RemoteDeletionOutcome.FAILED, error.code
        except (OSError, ValueError):
            outcome, error_code = RemoteDeletionOutcome.UNKNOWN, "remote_deletion_unknown"
        if cancellation.cancelled:
            raise OperationCancelled("remote deletion cancelled")
        result = RemoteDeletionResult(
            "1.0", request.request_id, request.request_hash, request.backup_id,
            request.host_id, request.host_fingerprint, request.manifest_hash,
            request.remote_receipt_hash, request.key_reference, outcome, error_code,
            self.clock(),
        ).with_hash()
        content = encode_remote_deletion_result(result)
        _atomic_write(result_path, content, 0o600)
        os.chown(result_path, self.invoking_uid, -1, follow_symlinks=False)
        return content

    def _directory(self, path: Path) -> None:
        if path.is_symlink() or not path.is_dir():
            raise AdapterError("unsafe_remote_staging", "deletion staging directory is unsafe")
        metadata = path.stat(follow_symlinks=False)
        if metadata.st_uid != self.invoking_uid or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise AdapterError("unsafe_remote_staging", "deletion staging metadata is unsafe")

    def _file(self, path: Path) -> bytes:
        if path.is_symlink() or not path.is_file():
            raise AdapterError("unsafe_remote_staging", "deletion request is missing or unsafe")
        metadata = path.stat(follow_symlinks=False)
        if (metadata.st_uid != self.invoking_uid or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_size > MAX_REMOTE_DELETION_BYTES):
            raise AdapterError("unsafe_remote_staging", "deletion request metadata is unsafe")
        return path.read_bytes()


def new_remote_deletion_request(request_id, manifest, receipt, *, now=None):
    current = now or utc_now()
    request = RemoteDeletionRequest(
        "1.0", REMOTE_DELETION_PROTOCOL_VERSION, REMOTE_DELETION_OPERATION,
        request_id, manifest.backup_id, manifest.host_id, manifest.host_fingerprint or "",
        manifest.manifest_hash, receipt.receipt_hash, receipt.key_reference,
        receipt.storage_location, receipt.item_hashes, current,
        current + timedelta(minutes=5),
    ).with_hash()
    _validate_request(request, request.request_hash, current)
    return request


def encode_remote_deletion_request(request: RemoteDeletionRequest) -> bytes:
    _validate_request(request, request.request_hash, request.created_at)
    return _bounded(_bytes(request))


def decode_remote_deletion_request(content: bytes, *, expected_hash: str,
                                   now: datetime) -> RemoteDeletionRequest:
    value = _load(content)
    expected = {"backup_id", "created_at", "expires_at", "host_fingerprint", "host_id",
                "item_hashes", "key_reference", "manifest_hash", "operation",
                "protocol_version", "remote_receipt_hash", "request_hash", "request_id",
                "schema_version", "storage_location"}
    if set(value) != expected:
        raise AdapterError("invalid_remote_deletion", "deletion request fields are invalid")
    try:
        request = RemoteDeletionRequest(
            _text(value, "schema_version"), int(value["protocol_version"]),
            _text(value, "operation"), _text(value, "request_id"),
            _text(value, "backup_id"), _text(value, "host_id"),
            _text(value, "host_fingerprint"), _text(value, "manifest_hash"),
            _text(value, "remote_receipt_hash"), _text(value, "key_reference"),
            _text(value, "storage_location"), _items(value["item_hashes"]),
            datetime.fromisoformat(_text(value, "created_at")),
            datetime.fromisoformat(_text(value, "expires_at")),
            _text(value, "request_hash"),
        )
    except (TypeError, ValueError) as error:
        raise AdapterError("invalid_remote_deletion", "deletion request is malformed") from error
    if content != _bytes(request):
        raise AdapterError("invalid_remote_deletion", "deletion request is not canonical")
    _validate_request(request, expected_hash, now)
    return request


def encode_remote_deletion_result(result: RemoteDeletionResult) -> bytes:
    _validate_result(result)
    return _bounded(_bytes(result))


def decode_remote_deletion_result(content: bytes) -> RemoteDeletionResult:
    value = _load(content)
    expected = {"backup_id", "completed_at", "error_code", "host_fingerprint", "host_id",
                "key_reference", "manifest_hash", "outcome", "remote_receipt_hash",
                "request_hash", "request_id", "result_hash", "schema_version"}
    if set(value) != expected:
        raise AdapterError("invalid_remote_deletion_result", "deletion result fields are invalid")
    try:
        result = RemoteDeletionResult(
            _text(value, "schema_version"), _text(value, "request_id"),
            _text(value, "request_hash"), _text(value, "backup_id"),
            _text(value, "host_id"), _text(value, "host_fingerprint"),
            _text(value, "manifest_hash"), _text(value, "remote_receipt_hash"),
            _text(value, "key_reference"), RemoteDeletionOutcome(_text(value, "outcome")),
            value["error_code"] if isinstance(value["error_code"], str) else None,
            datetime.fromisoformat(_text(value, "completed_at")), _text(value, "result_hash"),
        )
    except (TypeError, ValueError) as error:
        raise AdapterError("invalid_remote_deletion_result", "deletion result is malformed") from error
    if content != _bytes(result):
        raise AdapterError("invalid_remote_deletion_result", "deletion result is not canonical")
    _validate_result(result)
    return result


def _validate_request(request, expected_hash, now):
    if (request.schema_version != "1.0" or request.protocol_version != 1
            or request.operation != REMOTE_DELETION_OPERATION
            or not all(_IDENTIFIER.fullmatch(item) for item in
                       (request.request_id, request.backup_id, request.host_id, request.key_reference))
            or not _FINGERPRINT.fullmatch(request.host_fingerprint)
            or not all(_DIGEST.fullmatch(item) for item in
                       (request.manifest_hash, request.remote_receipt_hash, request.request_hash))
            or request.request_hash != expected_hash
            or not request.storage_location.startswith("/var/lib/llm-manager/backups/")
            or not request.item_hashes):
        raise AdapterError("invalid_remote_deletion", "deletion request identity is invalid")
    if any(not target or (digest is not None and not _DIGEST.fullmatch(digest))
           for target, digest in request.item_hashes):
        raise AdapterError("invalid_remote_deletion", "deletion item identity is invalid")
    if (any(item.tzinfo is None for item in (request.created_at, request.expires_at, now))
            or not request.created_at <= now <= request.expires_at
            or request.expires_at - request.created_at > timedelta(minutes=5)):
        raise AdapterError("expired_remote_deletion", "deletion request is expired")
    if request.request_hash != hashlib.sha256(_bytes(replace(request, request_hash=""))).hexdigest():
        raise AdapterError("remote_deletion_hash_mismatch", "deletion request was modified")


def _validate_result(result):
    if (result.schema_version != "1.0" or not _IDENTIFIER.fullmatch(result.request_id)
            or not _IDENTIFIER.fullmatch(result.backup_id) or not _IDENTIFIER.fullmatch(result.host_id)
            or not _IDENTIFIER.fullmatch(result.key_reference)
            or not _FINGERPRINT.fullmatch(result.host_fingerprint)
            or not all(_DIGEST.fullmatch(item) for item in
                       (result.request_hash, result.manifest_hash,
                        result.remote_receipt_hash, result.result_hash))
            or result.completed_at.tzinfo is None
            or ((result.outcome in {RemoteDeletionOutcome.DELETED,
                                    RemoteDeletionOutcome.ALREADY_ABSENT}) != (result.error_code is None))
            or (result.error_code is not None and not _IDENTIFIER.fullmatch(result.error_code))):
        raise AdapterError("invalid_remote_deletion_result", "deletion result is invalid")
    expected = hashlib.sha256(_bytes(replace(result, result_hash=""))).hexdigest()
    if result.result_hash != expected:
        raise AdapterError("invalid_remote_deletion_result", "deletion result integrity failed")


def _bytes(value):
    return json.dumps(to_primitive(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _bounded(content):
    if len(content) > MAX_REMOTE_DELETION_BYTES:
        raise AdapterError("remote_deletion_too_large", "deletion payload exceeds 1 MiB")
    return content


def _load(content):
    _bounded(content)
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdapterError("invalid_remote_deletion", "deletion payload is malformed") from error
    if not isinstance(value, dict):
        raise AdapterError("invalid_remote_deletion", "deletion payload is not an object")
    return value


def _text(value, key):
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(key)
    return item


def _items(value):
    if not isinstance(value, list):
        raise ValueError("item_hashes")
    result = []
    for item in value:
        if (not isinstance(item, list) or len(item) != 2 or not isinstance(item[0], str)
                or (item[1] is not None and not isinstance(item[1], str))):
            raise ValueError("item_hashes")
        result.append((item[0], item[1]))
    return tuple(result)
