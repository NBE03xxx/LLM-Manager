from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Iterable, Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import BackupManifest
from llm_manager.domain.serialization import to_primitive

from .backup_deletion import (
    BackupDeletionView, CopyDeleteOutcome, validate_backup_deletion_result,
)
from .backup_reconciliation import CopyPresence, DualCopyState
from .remote_backup import RemoteRetentionRecord
from .remote_retention import (
    RemoteRetentionResult, RemoteRetentionState, encode_remote_retention_result,
)


class BackupListAction(StrEnum):
    START_DUAL_DELETE = "start_dual_delete"
    RETRY_REMOTE_DELETE = "retry_remote_delete"
    RECOVER_REMOTE_RESULT = "recover_remote_result"
    RETRY_LOCAL_DELETE = "retry_local_delete"
    RETRY_STAGING_CLEANUP = "retry_staging_cleanup"
    RECONCILE_COPIES = "reconcile_copies"


@dataclass(frozen=True, slots=True)
class RetentionRunEvidence:
    local_result: "LocalRetentionResult | None" = None
    remote_result: RemoteRetentionResult | None = None


@dataclass(frozen=True, slots=True)
class LocalRetentionResult:
    schema_version: str
    request_id: str
    host_id: str
    evaluated_at: datetime
    state: RemoteRetentionState
    removed_backup_ids: tuple[str, ...]
    remaining_backup_ids: tuple[str, ...]
    error_code: str | None
    result_hash: str = ""

    def with_hash(self) -> "LocalRetentionResult":
        value = replace(self, result_hash="")
        return replace(value, result_hash=hashlib.sha256(_canonical(value)).hexdigest())


class LocalRetentionBackend(Protocol):
    def list_manifests(self, host_id: str) -> tuple[BackupManifest, ...]: ...

    def prune(self, host_id: str, now: datetime | None = None,
              keep_generations: int = 10) -> tuple[str, ...]: ...


class LocalRetentionRunner:
    def __init__(self, backend: LocalRetentionBackend) -> None:
        self.backend = backend

    def prune(self, request_id: str, host_id: str,
              now: datetime) -> LocalRetentionResult:
        before = self._ids(host_id)
        try:
            removed = self.backend.prune(host_id, now=now, keep_generations=10)
            remaining = self._ids(host_id)
            observed = tuple(item for item in before if item not in remaining)
            if (len(set(before)) != len(before) or any(item not in before for item in remaining)
                    or tuple(removed) != observed):
                raise AdapterError("local_retention_reconciliation_mismatch",
                                   "local retention result changed identity")
            state, error = RemoteRetentionState.COMPLETED, None
        except (AdapterError, OSError, ValueError) as caught:
            error = getattr(caught, "code", "local_retention_failed")
            try:
                remaining = self._ids(host_id)
                removed = tuple(item for item in before if item not in remaining)
                state = RemoteRetentionState.PARTIAL if removed else RemoteRetentionState.FAILED
            except (AdapterError, OSError, ValueError):
                removed, remaining, state = (), (), RemoteRetentionState.UNKNOWN
        result = LocalRetentionResult(
            "1.0", request_id, host_id, now, state, tuple(removed),
            tuple(remaining), error,
        ).with_hash()
        _validate_local_retention(result)
        return result

    def _ids(self, host_id):
        values = self.backend.list_manifests(host_id)
        if any(item.host_id != host_id for item in values):
            raise AdapterError("local_retention_binding_mismatch", "local host changed")
        return tuple(item.backup_id for item in values)


@dataclass(frozen=True, slots=True)
class BackupInventoryItem:
    backup_id: str
    host_id: str
    created_at: datetime | None
    retention_expires_at: datetime | None
    protected: bool
    local_presence: CopyPresence
    remote_presence: CopyPresence
    state: DualCopyState
    requires_attention: bool
    local_retention_removed: bool
    remote_retention_removed: bool
    local_retention_state: RemoteRetentionState | None
    remote_retention_state: RemoteRetentionState | None
    deletion_view: BackupDeletionView | None
    allowed_actions: tuple[BackupListAction, ...]


class LocalBackupInventoryPort(Protocol):
    def list_manifests(self, host_id: str) -> tuple[BackupManifest, ...]: ...


class RemoteBackupInventoryPort(Protocol):
    def list_retention(
        self, host_id: str, *, expected_fingerprint: str | None = None
    ) -> tuple[RemoteRetentionRecord, ...]: ...


class BackupInventoryService:
    """Build display state from read-only observations and immutable operation evidence."""

    def __init__(self, local: LocalBackupInventoryPort,
                 remote: RemoteBackupInventoryPort) -> None:
        self.local = local
        self.remote = remote

    def list_for_host(
        self,
        host_id: str,
        host_fingerprint: str,
        cancellation: CancellationToken,
        *,
        deletion_views: Iterable[BackupDeletionView] = (),
        retention: RetentionRunEvidence | None = None,
    ) -> tuple[BackupInventoryItem, ...]:
        if cancellation.cancelled:
            raise OperationCancelled("backup inventory cancelled")
        local_values, local_unknown = self._local(host_id)
        if cancellation.cancelled:
            raise OperationCancelled("backup inventory cancelled")
        remote_values, remote_unknown = self._remote(host_id, host_fingerprint)
        views = self._views(host_id, host_fingerprint, deletion_views)
        evidence = retention or RetentionRunEvidence()
        self._validate_retention(host_id, host_fingerprint, evidence)
        identifiers = set(local_values) | set(remote_values) | set(views)
        if evidence.local_result is not None:
            identifiers.update(evidence.local_result.removed_backup_ids)
            identifiers.update(evidence.local_result.remaining_backup_ids)
        if evidence.remote_result is not None:
            identifiers.update(evidence.remote_result.removed_backup_ids)
            identifiers.update(evidence.remote_result.remaining_backup_ids)
        items = []
        for backup_id in identifiers:
            local = CopyPresence.UNKNOWN if local_unknown else (
                CopyPresence.PRESENT if backup_id in local_values else CopyPresence.ABSENT
            )
            remote = CopyPresence.UNKNOWN if remote_unknown else (
                CopyPresence.PRESENT if backup_id in remote_values else CopyPresence.ABSENT
            )
            state = _state(local, remote)
            manifest = local_values.get(backup_id)
            record = remote_values.get(backup_id)
            view = views.get(backup_id)
            protected = bool(
                (manifest is not None and manifest.protected)
                or (record is not None and record.protected)
            )
            remote_removed = bool(
                evidence.remote_result is not None
                and backup_id in evidence.remote_result.removed_backup_ids
            )
            remote_state = (
                evidence.remote_result.state if evidence.remote_result is not None
                and backup_id in {
                    *evidence.remote_result.removed_backup_ids,
                    *evidence.remote_result.remaining_backup_ids,
                } else None
            )
            local_state = (
                evidence.local_result.state if evidence.local_result is not None
                and backup_id in {
                    *evidence.local_result.removed_backup_ids,
                    *evidence.local_result.remaining_backup_ids,
                } else None
            )
            attention = (
                state not in {DualCopyState.BOTH_AVAILABLE, DualCopyState.BOTH_DELETED}
                or (view is not None and view.result.requires_attention)
                or remote_state in {
                    RemoteRetentionState.PARTIAL, RemoteRetentionState.FAILED,
                    RemoteRetentionState.UNKNOWN,
                }
                or local_state in {
                    RemoteRetentionState.PARTIAL, RemoteRetentionState.FAILED,
                    RemoteRetentionState.UNKNOWN,
                }
            )
            actions = _actions(state, protected, view, local_state, remote_state)
            items.append(BackupInventoryItem(
                backup_id, host_id,
                manifest.created_at if manifest is not None else (
                    record.created_at if record is not None else None
                ),
                manifest.retention_expires_at if manifest is not None else (
                    record.retention_expires_at if record is not None else None
                ),
                protected, local, remote, state, attention,
                bool(evidence.local_result is not None and
                     backup_id in evidence.local_result.removed_backup_ids), remote_removed,
                local_state, remote_state, view, actions,
            ))
        return tuple(sorted(items, key=lambda item: (
            item.created_at is not None, item.created_at or datetime.min,
            item.backup_id,
        ), reverse=True))

    def _local(self, host_id):
        try:
            values = self.local.list_manifests(host_id)
            if (len({item.backup_id for item in values}) != len(values)
                    or any(item.host_id != host_id for item in values)):
                raise AdapterError("backup_inventory_binding_mismatch", "local host changed")
            return {item.backup_id: item for item in values}, False
        except (AdapterError, OSError, ValueError):
            return {}, True

    def _remote(self, host_id, fingerprint):
        try:
            values = self.remote.list_retention(
                host_id, expected_fingerprint=fingerprint
            )
            if (len({item.backup_id for item in values}) != len(values)
                    or any(item.host_id != host_id for item in values)):
                raise AdapterError("backup_inventory_binding_mismatch", "remote host changed")
            return {item.backup_id: item for item in values}, False
        except (AdapterError, OSError, ValueError):
            return {}, True

    @staticmethod
    def _views(host_id, fingerprint, deletion_views):
        result = {}
        for view in deletion_views:
            validate_backup_deletion_result(view.result)
            if (view.result.host_id != host_id
                    or view.result.host_fingerprint != fingerprint
                    or view.result.backup_id in result):
                raise AdapterError("backup_inventory_binding_mismatch", "deletion view changed identity")
            result[view.result.backup_id] = view
        return result

    @staticmethod
    def _validate_retention(host_id, fingerprint, evidence):
        local = evidence.local_result
        if local is not None:
            _validate_local_retention(local)
            if local.host_id != host_id:
                raise AdapterError("backup_inventory_binding_mismatch", "local retention host changed")
        result = evidence.remote_result
        if result is not None:
            encode_remote_retention_result(result)
            if result.host_id != host_id or result.host_fingerprint != fingerprint:
                raise AdapterError("backup_inventory_binding_mismatch", "retention host changed")


def _actions(state, protected, view, local_retention_state, remote_retention_state):
    actions: list[BackupListAction] = []
    if state is DualCopyState.UNKNOWN or remote_retention_state in {
        RemoteRetentionState.PARTIAL, RemoteRetentionState.FAILED,
        RemoteRetentionState.UNKNOWN,
    } or local_retention_state in {
        RemoteRetentionState.PARTIAL, RemoteRetentionState.FAILED,
        RemoteRetentionState.UNKNOWN,
    }:
        actions.append(BackupListAction.RECONCILE_COPIES)
    if view is not None and view.staging_cleanup_pending:
        actions.append(BackupListAction.RETRY_STAGING_CLEANUP)
    if protected:
        return tuple(actions)
    if view is None:
        if state is DualCopyState.BOTH_AVAILABLE:
            actions.append(BackupListAction.START_DUAL_DELETE)
        return tuple(actions)
    result = view.result
    if result.remote_outcome is CopyDeleteOutcome.UNKNOWN:
        actions.append(BackupListAction.RECOVER_REMOTE_RESULT)
    elif result.remote_outcome is CopyDeleteOutcome.FAILED:
        if state is DualCopyState.BOTH_AVAILABLE:
            actions.append(BackupListAction.RETRY_REMOTE_DELETE)
    elif result.local_outcome is CopyDeleteOutcome.FAILED:
        if state is DualCopyState.LOCAL_ONLY:
            actions.append(BackupListAction.RETRY_LOCAL_DELETE)
    return tuple(dict.fromkeys(actions))


def _state(local, remote):
    if CopyPresence.UNKNOWN in {local, remote}:
        return DualCopyState.UNKNOWN
    if local is CopyPresence.PRESENT and remote is CopyPresence.PRESENT:
        return DualCopyState.BOTH_AVAILABLE
    if local is CopyPresence.PRESENT:
        return DualCopyState.LOCAL_ONLY
    if remote is CopyPresence.PRESENT:
        return DualCopyState.REMOTE_ONLY
    return DualCopyState.BOTH_DELETED


def _validate_local_retention(result):
    if (result.schema_version != "1.0" or not result.request_id or not result.host_id
            or result.evaluated_at.tzinfo is None
            or len(set(result.removed_backup_ids)) != len(result.removed_backup_ids)
            or len(set(result.remaining_backup_ids)) != len(result.remaining_backup_ids)
            or set(result.removed_backup_ids) & set(result.remaining_backup_ids)
            or (result.state is RemoteRetentionState.COMPLETED) != (result.error_code is None)
            or (result.state is RemoteRetentionState.PARTIAL and not result.removed_backup_ids)
            or (result.state in {RemoteRetentionState.FAILED, RemoteRetentionState.UNKNOWN}
                and bool(result.removed_backup_ids))
            or (result.state is RemoteRetentionState.UNKNOWN and bool(result.remaining_backup_ids))):
        raise AdapterError("invalid_local_retention_result", "local retention result is invalid")
    expected = hashlib.sha256(_canonical(replace(result, result_hash=""))).hexdigest()
    if result.result_hash != expected:
        raise AdapterError("invalid_local_retention_result", "local retention integrity failed")


def _canonical(value):
    return json.dumps(to_primitive(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
