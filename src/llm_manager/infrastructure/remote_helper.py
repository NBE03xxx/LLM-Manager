from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import BackupManifest, utc_now
from llm_manager.domain.serialization import to_primitive

from .backup import BackupRestoreItem, _safe_component
from .remote_backup import (
    RemoteRecoveryReceipt,
    decode_remote_receipt,
    remote_storage_location,
)


REMOTE_HELPER_PROTOCOL_VERSION = 1
REMOTE_HELPER_OPERATION = "create_recovery_copy"
MAX_REMOTE_REQUEST_BYTES = 1024 * 1024
MAX_REMOTE_REQUEST_LIFETIME = timedelta(minutes=10)
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


@dataclass(frozen=True, slots=True)
class RemoteRecoveryRequest:
    protocol_version: int
    operation: str
    request_id: str
    backup_id: str
    plan_id: str
    change_set_hash: str
    host_id: str
    host_fingerprint: str
    local_manifest_hash: str
    storage_location: str
    key_reference: str
    key_scope: str
    item_hashes: tuple[tuple[str, str | None], ...]
    backup_created_at: datetime
    retention_expires_at: datetime
    protected: bool
    requested_at: datetime
    expires_at: datetime
    request_hash: str = ""

    def with_hash(self) -> "RemoteRecoveryRequest":
        value = replace(self, request_hash="")
        return replace(value, request_hash=hashlib.sha256(_request_bytes(value)).hexdigest())


class RemoteRecoveryTransport(Protocol):
    """User-side staging and a fixed remote-helper invocation; no argv or shell input."""

    def create_recovery_copy(
        self,
        request_content: bytes,
        staged_items: tuple[BackupRestoreItem, ...],
        cancellation: CancellationToken,
    ) -> bytes: ...

    def read_recovery_receipt(
        self,
        request_content: bytes,
        cancellation: CancellationToken,
    ) -> bytes: ...


class RemoteHelperRecoveryCopyStore:
    """RemoteRecoveryCopyPort backed by a narrowly scoped remote helper transport."""

    def __init__(
        self,
        transport: RemoteRecoveryTransport,
        key_reference: str,
        *,
        clock=utc_now,
    ) -> None:
        if not key_reference or not _IDENTIFIER.fullmatch(key_reference):
            raise ValueError("remote key reference must be a safe identifier")
        self.transport = transport
        self.key_reference = key_reference
        self.clock = clock
        self._requests: dict[tuple[str, str, str], RemoteRecoveryRequest] = {}

    def create(
        self,
        manifest: BackupManifest,
        items: tuple[BackupRestoreItem, ...],
        cancellation: CancellationToken,
    ) -> RemoteRecoveryReceipt:
        request = self._request(manifest)
        _validate_staged_items(request, items)
        content = encode_remote_request(request)
        # Preserve the exact staging identity before transport. If the helper
        # completes but receipt download disconnects, verify() can reconnect to
        # the same immutable result instead of minting a different request hash.
        self._requests[self._identity(manifest)] = request
        _cancel(cancellation)
        receipt = decode_remote_receipt(
            self.transport.create_recovery_copy(content, items, cancellation)
        )
        _validate_response(request, receipt)
        return receipt

    def load(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> RemoteRecoveryReceipt:
        request = self._requests.get(self._identity(manifest))
        if request is None:
            raise AdapterError(
                "remote_request_identity_unavailable",
                "remote recovery request identity is unavailable",
            )
        content = encode_remote_request(request)
        _cancel(cancellation)
        receipt = decode_remote_receipt(
            self.transport.read_recovery_receipt(content, cancellation)
        )
        _validate_response(request, receipt)
        return receipt

    @staticmethod
    def _identity(manifest: BackupManifest) -> tuple[str, str, str]:
        return manifest.host_id, manifest.backup_id, manifest.manifest_hash

    def _request(self, manifest: BackupManifest) -> RemoteRecoveryRequest:
        now = self.clock()
        request = RemoteRecoveryRequest(
            REMOTE_HELPER_PROTOCOL_VERSION,
            REMOTE_HELPER_OPERATION,
            manifest.backup_id,
            manifest.backup_id,
            manifest.plan_id,
            manifest.change_set_hash,
            manifest.host_id,
            manifest.host_fingerprint or "",
            manifest.manifest_hash,
            remote_storage_location(manifest),
            self.key_reference,
            "remote_root",
            tuple((item.target, item.sha256) for item in manifest.items),
            manifest.created_at,
            manifest.retention_expires_at or manifest.created_at + timedelta(days=30),
            manifest.protected,
            now,
            now + timedelta(minutes=5),
        ).with_hash()
        validate_remote_request(request, request.request_hash, now=now)
        return request


def encode_remote_request(request: RemoteRecoveryRequest) -> bytes:
    validate_remote_request(request, request.request_hash, now=request.requested_at)
    content = _request_bytes(request)
    if len(content) > MAX_REMOTE_REQUEST_BYTES:
        raise AdapterError("remote_request_too_large", "remote helper request exceeds 1 MiB")
    return content


def decode_remote_request(
    content: bytes, *, expected_hash: str, now: datetime
) -> RemoteRecoveryRequest:
    if len(content) > MAX_REMOTE_REQUEST_BYTES:
        raise AdapterError("remote_request_too_large", "remote helper request exceeds 1 MiB")
    try:
        request = _decode_request(json.loads(content.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise AdapterError("invalid_remote_request", "remote helper request is malformed") from error
    if content != _request_bytes(request):
        raise AdapterError("invalid_remote_request", "remote helper request is not canonical")
    validate_remote_request(request, expected_hash, now=now)
    return request


def validate_remote_request(
    request: RemoteRecoveryRequest, expected_hash: str, *, now: datetime
) -> None:
    if request.protocol_version != REMOTE_HELPER_PROTOCOL_VERSION:
        raise AdapterError("unsupported_remote_protocol", "remote helper protocol is unsupported")
    if request.operation != REMOTE_HELPER_OPERATION:
        raise AdapterError("remote_operation_not_allowed", "remote helper operation is not allowlisted")
    for value in (request.request_id, request.backup_id, request.plan_id, request.host_id, request.key_reference):
        if not _IDENTIFIER.fullmatch(value):
            raise AdapterError("invalid_remote_identifier", "remote helper identifier is invalid")
    for digest in (request.change_set_hash, request.local_manifest_hash, request.request_hash, expected_hash):
        _digest(digest)
    if not request.host_fingerprint or request.key_scope != "remote_root":
        raise AdapterError("invalid_remote_binding", "remote host fingerprint and root key scope are required")
    if request.storage_location != f"/var/lib/llm-manager/backups/{_safe_component(request.host_id)}/{request.backup_id}":
        raise AdapterError("invalid_remote_location", "remote storage location is not fixed")
    expected = hashlib.sha256(_request_bytes(replace(request, request_hash=""))).hexdigest()
    if request.request_hash != expected_hash or request.request_hash != expected:
        raise AdapterError("remote_request_hash_mismatch", "remote helper request integrity check failed")
    if request.requested_at.tzinfo is None or request.expires_at.tzinfo is None:
        raise AdapterError("invalid_remote_expiry", "remote helper timestamps require timezone")
    lifetime = request.expires_at - request.requested_at
    if lifetime <= timedelta(0) or lifetime > MAX_REMOTE_REQUEST_LIFETIME or now < request.requested_at or now >= request.expires_at:
        raise AdapterError("expired_remote_request", "remote helper request is outside its validity window")
    if (
        request.backup_created_at.tzinfo is None
        or request.retention_expires_at.tzinfo is None
        or request.retention_expires_at != request.backup_created_at + timedelta(days=30)
        or type(request.protected) is not bool
    ):
        raise AdapterError("invalid_remote_retention", "remote retention metadata is invalid")
    if len({target for target, _ in request.item_hashes}) != len(request.item_hashes):
        raise AdapterError("invalid_remote_items", "remote recovery items must be unique")
    for target, digest in request.item_hashes:
        if not target or (digest is not None and _digest(digest) != digest):
            raise AdapterError("invalid_remote_items", "remote recovery item identity is invalid")


def _validate_response(request: RemoteRecoveryRequest, receipt: RemoteRecoveryReceipt) -> None:
    if (
        receipt.backup_id != request.backup_id
        or receipt.plan_id != request.plan_id
        or receipt.change_set_hash != request.change_set_hash
        or receipt.host_id != request.host_id
        or receipt.host_fingerprint != request.host_fingerprint
        or receipt.local_manifest_hash != request.local_manifest_hash
        or receipt.storage_location != request.storage_location
        or receipt.key_reference != request.key_reference
        or receipt.key_scope != request.key_scope
        or receipt.item_hashes != request.item_hashes
    ):
        raise AdapterError("remote_response_binding_mismatch", "remote receipt does not match its request")


def _validate_staged_items(
    request: RemoteRecoveryRequest, items: tuple[BackupRestoreItem, ...]
) -> None:
    if tuple((item.target, item.sha256) for item in items) != request.item_hashes:
        raise AdapterError("remote_staging_mismatch", "staged recovery items do not match the request")
    for item in items:
        if item.existed:
            if item.content is None or hashlib.sha256(item.content).hexdigest() != item.sha256:
                raise AdapterError("remote_staging_mismatch", "staged recovery content hash is invalid")
        elif item.content is not None or item.sha256 is not None:
            raise AdapterError("remote_staging_mismatch", "absent recovery item unexpectedly has content")


def _request_bytes(request: RemoteRecoveryRequest) -> bytes:
    return json.dumps(to_primitive(request), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode_request(value: object) -> RemoteRecoveryRequest:
    expected = {
        "backup_id", "change_set_hash", "expires_at", "host_fingerprint", "host_id",
        "item_hashes", "key_reference", "key_scope", "local_manifest_hash", "operation",
        "plan_id", "protocol_version", "request_hash", "request_id", "requested_at",
        "storage_location", "backup_created_at", "retention_expires_at", "protected",
    }
    if (
        not isinstance(value, dict) or set(value) != expected
        or type(value["protocol_version"]) is not int or type(value["protected"]) is not bool
    ):
        raise ValueError("invalid remote request fields")
    hashes = value["item_hashes"]
    if not isinstance(hashes, list) or any(not isinstance(item, list) or len(item) != 2 for item in hashes):
        raise ValueError("invalid remote item hashes")
    string_keys = expected - {"protocol_version", "item_hashes", "protected"}
    if any(not isinstance(value[key], str) for key in string_keys):
        raise ValueError("invalid remote request strings")
    return RemoteRecoveryRequest(
        value["protocol_version"], value["operation"], value["request_id"], value["backup_id"],
        value["plan_id"], value["change_set_hash"], value["host_id"], value["host_fingerprint"],
        value["local_manifest_hash"], value["storage_location"], value["key_reference"],
        value["key_scope"], tuple((item[0], item[1]) for item in hashes),
        datetime.fromisoformat(value["backup_created_at"]),
        datetime.fromisoformat(value["retention_expires_at"]), value["protected"],
        datetime.fromisoformat(value["requested_at"]), datetime.fromisoformat(value["expires_at"]),
        value["request_hash"],
    )


def _digest(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise AdapterError("invalid_remote_hash", "remote helper request contains an invalid hash")
    return value


def _cancel(cancellation: CancellationToken) -> None:
    if cancellation.cancelled:
        raise OperationCancelled("remote helper operation cancelled")
