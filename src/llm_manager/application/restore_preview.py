from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from llm_manager.application.errors import AdapterError
from llm_manager.domain.models import BackupManifest, utc_now
from llm_manager.domain.serialization import to_primitive


@dataclass(frozen=True, slots=True)
class RestorePreviewItem:
    target: str
    existed: bool
    sha256: str | None
    mode: int | None


@dataclass(frozen=True, slots=True)
class RestorePreview:
    host_id: str
    backup_id: str
    manifest_hash: str
    created_at: datetime
    expires_at: datetime
    protected: bool
    items: tuple[RestorePreviewItem, ...]
    preview_hash: str = ""

    def with_hash(self) -> "RestorePreview":
        value = replace(self, preview_hash="")
        return replace(value, preview_hash=hashlib.sha256(_canonical(value)).hexdigest())


@dataclass(frozen=True, slots=True)
class RestoreApproval:
    approval_id: str
    actor: str
    host_id: str
    backup_id: str
    manifest_hash: str
    preview_hash: str
    approved_at: datetime
    expires_at: datetime

    def is_valid_for(self, preview: RestorePreview, now: datetime | None = None) -> bool:
        current = now or utc_now()
        return (
            current < self.expires_at
            and self.host_id == preview.host_id
            and self.backup_id == preview.backup_id
            and self.manifest_hash == preview.manifest_hash
            and self.preview_hash == preview.preview_hash
            and preview.created_at <= current < preview.expires_at
        )


@dataclass(frozen=True, slots=True)
class CreateRestorePreview:
    lifetime: timedelta = timedelta(minutes=5)

    def execute(
        self, manifest: BackupManifest, now: datetime | None = None
    ) -> RestorePreview:
        current = now or utc_now()
        preview = RestorePreview(
            manifest.host_id,
            manifest.backup_id,
            manifest.manifest_hash,
            current,
            current + self.lifetime,
            manifest.protected,
            tuple(
                RestorePreviewItem(item.target, item.existed, item.sha256, item.mode)
                for item in manifest.items
            ),
        ).with_hash()
        if not preview.items or not preview.manifest_hash:
            raise AdapterError("invalid_restore_preview", "restore preview is incomplete")
        return preview


@dataclass(frozen=True, slots=True)
class CreateRestoreApproval:
    lifetime: timedelta = timedelta(minutes=5)

    def execute(
        self,
        preview: RestorePreview,
        approval_id: str,
        actor: str,
        explicit_review: bool,
        now: datetime | None = None,
    ) -> RestoreApproval:
        current = now or utc_now()
        if not explicit_review:
            raise AdapterError("explicit_restore_review_required", "restore review is required")
        if not approval_id.strip() or not actor.strip():
            raise AdapterError("approval_identity_required", "approval identity is required")
        if current >= preview.expires_at or preview.with_hash() != preview:
            raise AdapterError("stale_restore_preview", "restore preview is stale or invalid")
        approval = RestoreApproval(
            approval_id,
            actor,
            preview.host_id,
            preview.backup_id,
            preview.manifest_hash,
            preview.preview_hash,
            current,
            min(current + self.lifetime, preview.expires_at),
        )
        if not approval.is_valid_for(preview, current):
            raise AdapterError("invalid_restore_approval", "restore approval is invalid")
        return approval


def _canonical(value: object) -> bytes:
    return json.dumps(
        to_primitive(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
