from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Protocol

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.domain.enums import Severity, ValidationStatus
from llm_manager.domain.models import BackupManifest, LocalizedMessage, ValidationResult

from .backup import BackupRestoreItem, _safe_component


REMOTE_BACKUP_ROOT = "/var/lib/llm-manager/backups"


@dataclass(frozen=True, slots=True)
class RemoteRecoveryReceipt:
    schema_version: str
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
    verified: bool
    receipt_hash: str = ""

    def with_hash(self) -> "RemoteRecoveryReceipt":
        return replace(self, receipt_hash=_receipt_hash(self))


class RemoteRecoveryCopyPort(Protocol):
    def create(
        self,
        manifest: BackupManifest,
        items: tuple[BackupRestoreItem, ...],
        cancellation: CancellationToken,
    ) -> RemoteRecoveryReceipt: ...

    def load(
        self, backup_id: str, cancellation: CancellationToken
    ) -> RemoteRecoveryReceipt: ...


class LocalBackupForRemoteCopy(Protocol):
    def create(self, request: BackupRequest, cancellation: CancellationToken) -> BackupManifest: ...
    def verify(self, manifest: BackupManifest, cancellation: CancellationToken) -> tuple[ValidationResult, ...]: ...
    def restore_items(self, manifest: BackupManifest, cancellation: CancellationToken) -> tuple[BackupRestoreItem, ...]: ...


class DualCopyPrivilegedBackupStore:
    """Keep the local backup authoritative and require a verified remote copy."""

    def __init__(self, local: LocalBackupForRemoteCopy, remote: RemoteRecoveryCopyPort) -> None:
        self.local = local
        self.remote = remote

    def create(self, request: BackupRequest, cancellation: CancellationToken) -> BackupManifest:
        manifest = self.local.create(request, cancellation)
        try:
            items = self.local.restore_items(manifest, cancellation)
            receipt = self.remote.create(manifest, items, cancellation)
            _validate_receipt(manifest, receipt)
        except (AdapterError, OSError, ValueError):
            # Preserve the local authoritative backup. verify() will fail closed
            # and prevent Apply when the remote copy is missing or invalid.
            return manifest
        return manifest

    def verify(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> tuple[ValidationResult, ...]:
        local_results = self.local.verify(manifest, cancellation)
        try:
            receipt = self.remote.load(manifest.backup_id, cancellation)
            _validate_receipt(manifest, receipt)
            remote_result = _result(True, receipt.receipt_hash)
        except (AdapterError, OSError, ValueError) as error:
            remote_result = _result(False, getattr(error, "code", type(error).__name__))
        return local_results + (remote_result,)

    def restore_items(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> tuple[BackupRestoreItem, ...]:
        return self.local.restore_items(manifest, cancellation)


def _validate_receipt(manifest: BackupManifest, receipt: RemoteRecoveryReceipt) -> None:
    expected_items = tuple((item.target, item.sha256) for item in manifest.items)
    expected_location = remote_storage_location(manifest)
    if (
        receipt.schema_version != "1.0"
        or not receipt.verified
        or receipt.backup_id != manifest.backup_id
        or receipt.plan_id != manifest.plan_id
        or receipt.change_set_hash != manifest.change_set_hash
        or receipt.host_id != manifest.host_id
        or not manifest.host_fingerprint
        or receipt.host_fingerprint != manifest.host_fingerprint
        or receipt.local_manifest_hash != manifest.manifest_hash
        or receipt.storage_location != expected_location
        or receipt.key_scope != "remote_root"
        or not receipt.key_reference
        or receipt.key_reference == manifest.encryption.key_reference
        or receipt.item_hashes != expected_items
        or receipt.receipt_hash != _receipt_hash(replace(receipt, receipt_hash=""))
    ):
        raise AdapterError(
            "invalid_remote_backup_receipt",
            "remote recovery copy is not bound to the local backup",
        )


def remote_storage_location(manifest: BackupManifest) -> str:
    if not manifest.backup_id or "/" in manifest.backup_id or manifest.backup_id in {".", ".."}:
        raise AdapterError("invalid_backup_id", "backup ID is not a safe path component")
    return f"{REMOTE_BACKUP_ROOT}/{_safe_component(manifest.host_id)}/{manifest.backup_id}"


def _receipt_hash(receipt: RemoteRecoveryReceipt) -> str:
    value = replace(receipt, receipt_hash="")
    encoded = json.dumps(
        {
            "backup_id": value.backup_id,
            "change_set_hash": value.change_set_hash,
            "host_fingerprint": value.host_fingerprint,
            "host_id": value.host_id,
            "item_hashes": value.item_hashes,
            "key_reference": value.key_reference,
            "key_scope": value.key_scope,
            "local_manifest_hash": value.local_manifest_hash,
            "plan_id": value.plan_id,
            "receipt_hash": "",
            "schema_version": value.schema_version,
            "storage_location": value.storage_location,
            "verified": value.verified,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _result(passed: bool, actual: str) -> ValidationResult:
    return ValidationResult(
        "backup.remote-copy",
        "backup",
        "backup.remote-copy",
        ValidationStatus.PASSED if passed else ValidationStatus.FAILED,
        "verified",
        actual,
        Severity.INFO if passed else Severity.CRITICAL,
        LocalizedMessage("validation.backup.remote-copy"),
    )
