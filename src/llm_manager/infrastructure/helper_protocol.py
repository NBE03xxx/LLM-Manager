from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.domain.serialization import to_primitive
from llm_manager.planning.ollama import DROP_IN_PATH

PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 1024 * 1024
MAX_REQUEST_LIFETIME = timedelta(minutes=10)
OLLAMA_UNIT = "ollama.service"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


class HelperOperationKind(StrEnum):
    ATOMIC_REPLACE = "atomic_replace"
    REMOVE_CREATED_FILE = "remove_created_file"
    DAEMON_RELOAD = "daemon_reload"
    RESTART_UNIT = "restart_unit"
    RESTORE_FILE = "restore_file"


@dataclass(frozen=True, slots=True)
class HelperOperation:
    operation_id: str
    kind: HelperOperationKind
    target: str | None = None
    unit: str | None = None
    before_hash: str | None = None
    staged_content_hash: str | None = None
    expected_mode: int | None = None
    expected_uid: int | None = None
    expected_gid: int | None = None


@dataclass(frozen=True, slots=True)
class HelperRequest:
    protocol_version: int
    operation_id: str
    host_id: str
    plan_id: str
    change_set_hash: str
    operations: tuple[HelperOperation, ...]
    requested_at: datetime
    expires_at: datetime
    request_hash: str = ""
    approval_id: str | None = None
    backup_id: str | None = None
    manifest_hash: str | None = None

    def with_hash(self) -> "HelperRequest":
        return replace(self, request_hash=_hash(replace(self, request_hash="")))


def encode_request(request: HelperRequest) -> bytes:
    validate_request(request, request.request_hash, now=request.requested_at)
    encoded = _bytes(request)
    if len(encoded) > MAX_REQUEST_BYTES:
        raise AdapterError("request_too_large", "helper request exceeds 1 MiB")
    return encoded


def decode_request(content: bytes, *, expected_hash: str, now: datetime) -> HelperRequest:
    if len(content) > MAX_REQUEST_BYTES:
        raise AdapterError("request_too_large", "helper request exceeds 1 MiB")
    try:
        value = json.loads(content.decode("utf-8"))
        request = _decode(value)
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise AdapterError("invalid_helper_request", "helper request is malformed") from error
    if _bytes(request) != content:
        raise AdapterError("invalid_helper_request", "helper request is not canonical")
    validate_request(request, expected_hash, now=now)
    return request


def validate_request(request: HelperRequest, expected_hash: str, *, now: datetime) -> None:
    if request.protocol_version != PROTOCOL_VERSION:
        raise AdapterError("unsupported_protocol", "helper protocol version is unsupported")
    for value, name in (
        (request.operation_id, "operation_id"),
        (request.host_id, "host_id"),
        (request.plan_id, "plan_id"),
    ):
        if not _IDENTIFIER.fullmatch(value):
            raise AdapterError("invalid_identifier", f"helper {name} is invalid")
    _digest(request.change_set_hash)
    _digest(request.request_hash)
    _digest(expected_hash)
    if request.request_hash != expected_hash or _hash(replace(request, request_hash="")) != request.request_hash:
        raise AdapterError("request_hash_mismatch", "helper request integrity check failed")
    bindings = (request.approval_id, request.backup_id, request.manifest_hash)
    if any(value is not None for value in bindings) and not all(value is not None for value in bindings):
        raise AdapterError("invalid_workflow_binding", "helper workflow binding must be complete")
    if request.approval_id is not None and not _IDENTIFIER.fullmatch(request.approval_id):
        raise AdapterError("invalid_identifier", "helper approval_id is invalid")
    if request.backup_id is not None and not _IDENTIFIER.fullmatch(request.backup_id):
        raise AdapterError("invalid_identifier", "helper backup_id is invalid")
    if request.manifest_hash is not None:
        _digest(request.manifest_hash)
    if request.requested_at.tzinfo is None or request.expires_at.tzinfo is None:
        raise AdapterError("invalid_expiry", "helper request timestamps require timezone")
    lifetime = request.expires_at - request.requested_at
    if lifetime <= timedelta(0) or lifetime > MAX_REQUEST_LIFETIME or now < request.requested_at or now >= request.expires_at:
        raise AdapterError("expired_request", "helper request is outside its validity window")
    if not request.operations or len({item.operation_id for item in request.operations}) != len(request.operations):
        raise AdapterError("invalid_operations", "helper operations must be non-empty and unique")
    for operation in request.operations:
        _validate_operation(operation)


def _validate_operation(operation: HelperOperation) -> None:
    if not _IDENTIFIER.fullmatch(operation.operation_id) or not isinstance(operation.kind, HelperOperationKind):
        raise AdapterError("invalid_operation", "helper operation identity is invalid")
    file_kinds = {
        HelperOperationKind.ATOMIC_REPLACE,
        HelperOperationKind.REMOVE_CREATED_FILE,
        HelperOperationKind.RESTORE_FILE,
    }
    if operation.kind in file_kinds:
        if operation.target != DROP_IN_PATH or Path(operation.target).as_posix() != DROP_IN_PATH or operation.unit is not None:
            raise AdapterError("target_not_allowed", "helper file target is not allowlisted")
        if operation.before_hash is not None:
            _digest(operation.before_hash)
        if operation.kind in {HelperOperationKind.ATOMIC_REPLACE, HelperOperationKind.RESTORE_FILE}:
            _digest(operation.staged_content_hash)
            if operation.expected_mode != 0o644:
                raise AdapterError("invalid_metadata", "helper file mode is invalid")
            if operation.expected_uid != 0 or operation.expected_gid != 0:
                raise AdapterError("invalid_metadata", "helper file must be installed as root:root")
        elif operation.staged_content_hash is not None or operation.before_hash is None:
            raise AdapterError("invalid_operation", "remove operation requires only a before hash")
        if operation.kind is HelperOperationKind.REMOVE_CREATED_FILE and any(
            value is not None for value in (operation.expected_mode, operation.expected_uid, operation.expected_gid)
        ):
            raise AdapterError("invalid_metadata", "remove operation must not include metadata")
        return
    if operation.kind is HelperOperationKind.DAEMON_RELOAD:
        if any(value is not None for value in (operation.target, operation.unit, operation.before_hash, operation.staged_content_hash, operation.expected_mode, operation.expected_uid, operation.expected_gid)):
            raise AdapterError("invalid_operation", "daemon reload takes no parameters")
        return
    if operation.kind is HelperOperationKind.RESTART_UNIT:
        if operation.unit != OLLAMA_UNIT or any(value is not None for value in (operation.target, operation.before_hash, operation.staged_content_hash, operation.expected_mode, operation.expected_uid, operation.expected_gid)):
            raise AdapterError("unit_not_allowed", "helper service unit is not allowlisted")
        return
    raise AdapterError("unknown_operation", "helper operation is unsupported")


def _hash(request: HelperRequest) -> str:
    return hashlib.sha256(_bytes(request)).hexdigest()


def _bytes(request: HelperRequest) -> bytes:
    return json.dumps(to_primitive(request), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode(value: object) -> HelperRequest:
    if not isinstance(value, dict) or set(value) != {
        "approval_id", "backup_id", "change_set_hash", "expires_at", "host_id", "manifest_hash", "operation_id", "operations", "plan_id",
        "protocol_version", "request_hash", "requested_at",
    }:
        raise ValueError("invalid request fields")
    raw_operations = value["operations"]
    if not isinstance(raw_operations, list):
        raise ValueError("operations must be a list")
    operations = tuple(_decode_operation(item) for item in raw_operations)
    return HelperRequest(
        protocol_version=_integer(value, "protocol_version"),
        operation_id=_text(value, "operation_id"),
        host_id=_text(value, "host_id"),
        plan_id=_text(value, "plan_id"),
        change_set_hash=_text(value, "change_set_hash"),
        operations=operations,
        requested_at=_time(value, "requested_at"),
        expires_at=_time(value, "expires_at"),
        request_hash=_text(value, "request_hash"),
        approval_id=_optional_text(value, "approval_id"),
        backup_id=_optional_text(value, "backup_id"),
        manifest_hash=_optional_text(value, "manifest_hash"),
    )


def _decode_operation(value: object) -> HelperOperation:
    if not isinstance(value, dict) or set(value) != {
        "before_hash", "expected_gid", "expected_mode", "expected_uid", "kind", "operation_id", "staged_content_hash", "target", "unit",
    }:
        raise ValueError("invalid operation fields")
    return HelperOperation(
        operation_id=_text(value, "operation_id"),
        kind=HelperOperationKind(_text(value, "kind")),
        target=_optional_text(value, "target"),
        unit=_optional_text(value, "unit"),
        before_hash=_optional_text(value, "before_hash"),
        staged_content_hash=_optional_text(value, "staged_content_hash"),
        expected_mode=_optional_integer(value, "expected_mode"),
        expected_uid=_optional_integer(value, "expected_uid"),
        expected_gid=_optional_integer(value, "expected_gid"),
    )


def _text(value: dict[str, object], key: str) -> str:
    item = value[key]
    if not isinstance(item, str) or not item:
        raise ValueError(f"invalid {key}")
    return item


def _optional_text(value: dict[str, object], key: str) -> str | None:
    item = value[key]
    if item is not None and not isinstance(item, str):
        raise ValueError(f"invalid {key}")
    return item


def _integer(value: dict[str, object], key: str) -> int:
    item = value[key]
    if type(item) is not int:
        raise ValueError(f"invalid {key}")
    return item


def _optional_integer(value: dict[str, object], key: str) -> int | None:
    item = value[key]
    if item is not None and type(item) is not int:
        raise ValueError(f"invalid {key}")
    return item


def _time(value: dict[str, object], key: str) -> datetime:
    return datetime.fromisoformat(_text(value, key))


def _digest(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise AdapterError("invalid_hash", "helper request contains an invalid sha256 hash")
    return value
