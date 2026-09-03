from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.application.restore_preview import (
    RestoreApproval,
    RestorePreview,
    RestorePreviewItem,
)
from llm_manager.domain.models import BackupManifest, utc_now
from llm_manager.domain.serialization import to_primitive


class StrictManifestInventory(Protocol):
    def list_manifests_strict(self, host_id: str) -> tuple[BackupManifest, ...]: ...


@dataclass(frozen=True, slots=True)
class PreparedRestoreAuthorization:
    host_id: str
    backup_id: str
    manifest_hash: str
    preview_hash: str
    approval_id: str
    actor: str
    targets: tuple[str, ...]
    prepared_at: datetime
    expires_at: datetime
    authorization_hash: str = ""

    def with_hash(self) -> "PreparedRestoreAuthorization":
        value = replace(self, authorization_hash="")
        return replace(value, authorization_hash=hashlib.sha256(_canonical(value)).hexdigest())


@dataclass(slots=True)
class PrepareLocalRestore:
    manifests: StrictManifestInventory

    def execute(
        self,
        host_id: str,
        backup_id: str,
        preview: RestorePreview,
        approval: RestoreApproval,
        cancellation: CancellationToken,
        now: datetime | None = None,
    ) -> PreparedRestoreAuthorization:
        current = now or utc_now()
        if cancellation.cancelled:
            raise OperationCancelled("restore preparation cancelled")
        if (
            preview.with_hash() != preview
            or preview.host_id != host_id
            or preview.backup_id != backup_id
            or not approval.is_valid_for(preview, current)
        ):
            raise AdapterError("invalid_restore_approval", "restore approval is stale or mismatched")
        manifests = self.manifests.list_manifests_strict(host_id)
        if cancellation.cancelled:
            raise OperationCancelled("restore preparation cancelled")
        manifest = next((item for item in manifests if item.backup_id == backup_id), None)
        if manifest is None:
            raise AdapterError("backup_not_found", "approved backup is unavailable")
        expected_items = tuple(
            RestorePreviewItem(item.target, item.existed, item.sha256, item.mode)
            for item in manifest.items
        )
        if (
            manifest.host_id != host_id
            or manifest.backup_id != backup_id
            or manifest.manifest_hash != preview.manifest_hash
            or manifest.protected != preview.protected
            or expected_items != preview.items
        ):
            raise AdapterError("restore_binding_mismatch", "manifest changed after restore review")
        prepared = PreparedRestoreAuthorization(
            host_id,
            backup_id,
            manifest.manifest_hash,
            preview.preview_hash,
            approval.approval_id,
            approval.actor,
            tuple(item.target for item in manifest.items),
            current,
            min(preview.expires_at, approval.expires_at),
        ).with_hash()
        if current >= prepared.expires_at:
            raise AdapterError("stale_restore_approval", "restore authorization expired")
        return prepared


def _canonical(value: object) -> bytes:
    return json.dumps(
        to_primitive(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
