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
from .remote_backup import RemoteRetentionRecord


REMOTE_RETENTION_PROTOCOL_VERSION = 1
REMOTE_RETENTION_OPERATION = "prune-retention"
MAX_REMOTE_RETENTION_BYTES = 1024 * 1024
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_FINGERPRINT = re.compile(r"SHA256:[A-Za-z0-9+/]{43}")


class RemoteRetentionState(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RemoteRetentionRequest:
    schema_version: str
    protocol_version: int
    operation: str
    request_id: str
    host_id: str
    host_fingerprint: str
    requested_at: datetime
    created_at: datetime
    expires_at: datetime
    request_hash: str = ""

    def with_hash(self) -> "RemoteRetentionRequest":
        value = replace(self, request_hash="")
        return replace(value, request_hash=hashlib.sha256(_bytes(value)).hexdigest())


@dataclass(frozen=True, slots=True)
class RemoteRetentionResult:
    schema_version: str
    request_id: str
    request_hash: str
    host_id: str
    host_fingerprint: str
    evaluated_at: datetime
    state: RemoteRetentionState
    removed_backup_ids: tuple[str, ...]
    remaining_backup_ids: tuple[str, ...]
    error_code: str | None
    result_hash: str = ""

    def with_hash(self) -> "RemoteRetentionResult":
        value = replace(self, result_hash="")
        return replace(value, result_hash=hashlib.sha256(_bytes(value)).hexdigest())


class RemoteRetentionBackend(Protocol):
    def list_retention(
        self, host_id: str, *, expected_fingerprint: str | None = None
    ) -> tuple[RemoteRetentionRecord, ...]: ...

    def prune(
        self, host_id: str, *, now: datetime, keep_generations: int = 10,
        expected_fingerprint: str | None = None,
    ) -> tuple[str, ...]: ...


class RemoteRetentionHelperExecutor:
    def __init__(
        self,
        staging_root: Path,
        backend: RemoteRetentionBackend,
        invoking_uid: int,
        *,
        clock=utc_now,
    ) -> None:
        self.staging_root = staging_root.absolute()
        self.backend = backend
        self.invoking_uid = invoking_uid
        self.clock = clock

    def execute(
        self, request_id: str, request_hash: str, cancellation: CancellationToken
    ) -> bytes:
        if not _IDENTIFIER.fullmatch(request_id) or not _DIGEST.fullmatch(request_hash):
            raise AdapterError("invalid_remote_retention_identity", "retention identity is invalid")
        directory = self.staging_root / request_id / request_hash
        self._directory(self.staging_root)
        self._directory(directory.parent)
        self._directory(directory)
        if not _within(directory.resolve(), self.staging_root.resolve()):
            raise AdapterError("unsafe_remote_staging", "retention staging escaped its root")
        request = decode_remote_retention_request(
            self._file(directory / "request.json"),
            expected_hash=request_hash,
            now=self.clock(),
        )
        if request.request_id != request_id:
            raise AdapterError("remote_retention_binding_mismatch", "request identity changed")
        result_path = directory / "result.json"
        if result_path.exists() or result_path.is_symlink():
            raise AdapterError("remote_result_exists", "remote retention result is immutable")
        before = self._records(request)
        try:
            removed = self.backend.prune(
                request.host_id,
                now=request.requested_at,
                keep_generations=10,
                expected_fingerprint=request.host_fingerprint,
            )
            remaining = self._records(request)
            observed_removed = tuple(item for item in before if item not in remaining)
            if (
                len(set(before)) != len(before)
                or any(item not in before for item in remaining)
                or tuple(removed) != observed_removed
            ):
                raise AdapterError(
                    "remote_retention_reconciliation_mismatch",
                    "retention backend result does not match read-only reconciliation",
                )
            state = RemoteRetentionState.COMPLETED
            error_code = None
        except OperationCancelled:
            raise
        except (AdapterError, OSError, ValueError) as error:
            error_code = getattr(error, "code", "remote_retention_failed")
            try:
                remaining = self._records(request)
                removed = tuple(item for item in before if item not in remaining)
                state = (
                    RemoteRetentionState.PARTIAL
                    if removed else RemoteRetentionState.FAILED
                )
            except (AdapterError, OSError, ValueError):
                removed = ()
                remaining = ()
                state = RemoteRetentionState.UNKNOWN
        if cancellation.cancelled:
            raise OperationCancelled("remote retention cancelled")
        result = RemoteRetentionResult(
            "1.0", request.request_id, request.request_hash, request.host_id,
            request.host_fingerprint, self.clock(), state, tuple(removed),
            tuple(remaining), error_code,
        ).with_hash()
        content = encode_remote_retention_result(result)
        _atomic_write(result_path, content, 0o600)
        os.chown(result_path, self.invoking_uid, -1, follow_symlinks=False)
        return content

    def _records(self, request: RemoteRetentionRequest) -> tuple[str, ...]:
        return tuple(
            item.backup_id for item in self.backend.list_retention(
                request.host_id, expected_fingerprint=request.host_fingerprint
            )
        )

    def _directory(self, path: Path) -> None:
        if path.is_symlink() or not path.is_dir():
            raise AdapterError("unsafe_remote_staging", "retention staging directory is unsafe")
        metadata = path.stat(follow_symlinks=False)
        if metadata.st_uid != self.invoking_uid or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise AdapterError("unsafe_remote_staging", "retention staging owner or mode is unsafe")

    def _file(self, path: Path) -> bytes:
        if path.is_symlink() or not path.is_file():
            raise AdapterError("unsafe_remote_staging", "retention request is missing or unsafe")
        metadata = path.stat(follow_symlinks=False)
        if (
            metadata.st_uid != self.invoking_uid
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > MAX_REMOTE_RETENTION_BYTES
        ):
            raise AdapterError("unsafe_remote_staging", "retention request metadata is unsafe")
        return path.read_bytes()


def encode_remote_retention_request(request: RemoteRetentionRequest) -> bytes:
    _validate_request(request, request.request_hash, request.requested_at)
    return _bounded(_bytes(request))


def decode_remote_retention_request(
    content: bytes, *, expected_hash: str, now: datetime | None
) -> RemoteRetentionRequest:
    value = _load(content)
    expected = {
        "created_at", "expires_at", "host_fingerprint", "host_id", "operation",
        "protocol_version", "request_hash", "request_id", "requested_at", "schema_version",
    }
    if set(value) != expected:
        raise AdapterError("invalid_remote_retention", "retention request fields are invalid")
    try:
        request = RemoteRetentionRequest(
            _text(value, "schema_version"), int(value["protocol_version"]),
            _text(value, "operation"), _text(value, "request_id"),
            _text(value, "host_id"), _text(value, "host_fingerprint"),
            datetime.fromisoformat(_text(value, "requested_at")),
            datetime.fromisoformat(_text(value, "created_at")),
            datetime.fromisoformat(_text(value, "expires_at")),
            _text(value, "request_hash"),
        )
    except (TypeError, ValueError) as error:
        raise AdapterError("invalid_remote_retention", "retention request is malformed") from error
    if content != _bytes(request):
        raise AdapterError("invalid_remote_retention", "retention request is not canonical")
    _validate_request(request, expected_hash, now)
    return request


def encode_remote_retention_result(result: RemoteRetentionResult) -> bytes:
    _validate_result(result)
    return _bounded(_bytes(result))


def decode_remote_retention_result(content: bytes) -> RemoteRetentionResult:
    value = _load(content)
    expected = {
        "error_code", "evaluated_at", "host_fingerprint", "host_id",
        "remaining_backup_ids", "removed_backup_ids", "request_hash", "request_id",
        "result_hash", "schema_version", "state",
    }
    if set(value) != expected:
        raise AdapterError("invalid_remote_retention_result", "retention result fields are invalid")
    try:
        result = RemoteRetentionResult(
            _text(value, "schema_version"), _text(value, "request_id"),
            _text(value, "request_hash"), _text(value, "host_id"),
            _text(value, "host_fingerprint"),
            datetime.fromisoformat(_text(value, "evaluated_at")),
            RemoteRetentionState(_text(value, "state")),
            _string_tuple(value, "removed_backup_ids"),
            _string_tuple(value, "remaining_backup_ids"),
            value["error_code"] if isinstance(value["error_code"], str) else None,
            _text(value, "result_hash"),
        )
    except (TypeError, ValueError) as error:
        raise AdapterError("invalid_remote_retention_result", "retention result is malformed") from error
    if content != _bytes(result):
        raise AdapterError("invalid_remote_retention_result", "retention result is not canonical")
    _validate_result(result)
    return result


def _validate_request(request: RemoteRetentionRequest, expected_hash: str, now: datetime | None) -> None:
    if (
        request.schema_version != "1.0"
        or request.protocol_version != REMOTE_RETENTION_PROTOCOL_VERSION
        or request.operation != REMOTE_RETENTION_OPERATION
        or not _IDENTIFIER.fullmatch(request.request_id)
        or not _IDENTIFIER.fullmatch(request.host_id)
        or not _FINGERPRINT.fullmatch(request.host_fingerprint)
        or not _DIGEST.fullmatch(request.request_hash)
        or request.request_hash != expected_hash
    ):
        raise AdapterError("invalid_remote_retention", "retention request identity is invalid")
    timestamps = (request.requested_at, request.created_at, request.expires_at) + (
        () if now is None else (now,)
    )
    if any(item.tzinfo is None for item in timestamps):
        raise AdapterError("invalid_remote_retention", "retention timestamps require timezone")
    if (
        request.created_at > request.requested_at
        or request.requested_at > request.expires_at
        or request.expires_at - request.created_at > timedelta(minutes=5)
        or (now is not None and not request.created_at <= now <= request.expires_at)
        or (now is not None and abs(now - request.requested_at) > timedelta(minutes=1))
    ):
        raise AdapterError("expired_remote_retention", "retention request is outside its validity window")
    expected = hashlib.sha256(_bytes(replace(request, request_hash=""))).hexdigest()
    if request.request_hash != expected:
        raise AdapterError("remote_retention_hash_mismatch", "retention request was modified")


def _validate_result(result: RemoteRetentionResult) -> None:
    if (
        result.schema_version != "1.0"
        or not _IDENTIFIER.fullmatch(result.request_id)
        or not _DIGEST.fullmatch(result.request_hash)
        or not _IDENTIFIER.fullmatch(result.host_id)
        or not _FINGERPRINT.fullmatch(result.host_fingerprint)
        or result.evaluated_at.tzinfo is None
        or len(set(result.removed_backup_ids)) != len(result.removed_backup_ids)
        or len(set(result.remaining_backup_ids)) != len(result.remaining_backup_ids)
        or set(result.removed_backup_ids) & set(result.remaining_backup_ids)
        or (result.state is RemoteRetentionState.COMPLETED) != (result.error_code is None)
        or (
            result.error_code is not None
            and not _IDENTIFIER.fullmatch(result.error_code)
        )
        or (
            result.state is RemoteRetentionState.PARTIAL
            and not result.removed_backup_ids
        )
        or (
            result.state in {RemoteRetentionState.FAILED, RemoteRetentionState.UNKNOWN}
            and bool(result.removed_backup_ids)
        )
        or (
            result.state is RemoteRetentionState.UNKNOWN
            and bool(result.remaining_backup_ids)
        )
    ):
        raise AdapterError("invalid_remote_retention_result", "retention result is invalid")
    if any(not _IDENTIFIER.fullmatch(item) for item in (*result.removed_backup_ids, *result.remaining_backup_ids)):
        raise AdapterError("invalid_remote_retention_result", "retention backup identity is invalid")
    expected = hashlib.sha256(_bytes(replace(result, result_hash=""))).hexdigest()
    if result.result_hash != expected:
        raise AdapterError("invalid_remote_retention_result", "retention result integrity failed")


def _bytes(value: object) -> bytes:
    return json.dumps(
        to_primitive(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _bounded(content: bytes) -> bytes:
    if len(content) > MAX_REMOTE_RETENTION_BYTES:
        raise AdapterError("remote_retention_too_large", "retention payload exceeds 1 MiB")
    return content


def _load(content: bytes) -> dict[str, object]:
    _bounded(content)
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdapterError("invalid_remote_retention", "retention payload is malformed") from error
    if not isinstance(value, dict):
        raise AdapterError("invalid_remote_retention", "retention payload is not an object")
    return value


def _text(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(key)
    return item


def _string_tuple(value: dict[str, object], key: str) -> tuple[str, ...]:
    item = value.get(key)
    if not isinstance(item, list) or any(not isinstance(entry, str) for entry in item):
        raise ValueError(key)
    return tuple(item)
