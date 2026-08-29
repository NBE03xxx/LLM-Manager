from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, HostPort
from llm_manager.domain.models import BackupManifest, utc_now
from llm_manager.domain.serialization import to_primitive

from .backup import _atomic_write, _manifest_hash, _within


class JournalStatus(StrEnum):
    APPLYING = "applying"
    VALIDATING = "validating"
    COMMITTED = "committed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    RECOVERY_REQUIRED = "recovery_required"


class ReconciliationState(StrEnum):
    UNAPPLIED = "unapplied"
    APPLIED = "applied"
    UNKNOWN = "unknown"


_TRANSITIONS: dict[JournalStatus, frozenset[JournalStatus]] = {
    JournalStatus.APPLYING: frozenset({JournalStatus.VALIDATING, JournalStatus.ROLLING_BACK}),
    JournalStatus.VALIDATING: frozenset({JournalStatus.COMMITTED, JournalStatus.ROLLING_BACK}),
    JournalStatus.ROLLING_BACK: frozenset({JournalStatus.ROLLED_BACK, JournalStatus.RECOVERY_REQUIRED}),
    JournalStatus.COMMITTED: frozenset(),
    JournalStatus.ROLLED_BACK: frozenset(),
    JournalStatus.RECOVERY_REQUIRED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class JournalTarget:
    target: str
    before_hash: str | None
    after_hash: str


@dataclass(frozen=True, slots=True)
class OperationJournal:
    operation_id: str
    schema_version: str
    plan_id: str
    host_id: str
    change_set_hash: str
    approval_id: str | None
    backup_id: str | None
    manifest_hash: str | None
    request_hash: str | None
    rollback_request_hash: str | None
    status: JournalStatus
    targets: tuple[JournalTarget, ...]
    created_at: datetime
    updated_at: datetime
    journal_hash: str


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    target: str
    state: ReconciliationState
    actual_hash: str | None


class LocalOperationJournal:
    def __init__(self, root: Path, allowed_roots: tuple[Path, ...]) -> None:
        self.root = root.resolve()
        self.allowed_roots = tuple(path.resolve() for path in allowed_roots)

    def create(
        self,
        operation_id: str,
        plan_id: str,
        host_id: str,
        change_set_hash: str,
        targets: tuple[JournalTarget, ...],
        *,
        approval_id: str | None = None,
        backup_id: str | None = None,
        manifest_hash: str | None = None,
        request_hash: str | None = None,
    ) -> OperationJournal:
        _component(operation_id)
        if not targets or len({item.target for item in targets}) != len(targets):
            raise AdapterError("invalid_journal", "journal targets must be non-empty and unique")
        for item in targets:
            self._target(item.target)
            _digest(item.after_hash)
            if item.before_hash is not None:
                _digest(item.before_hash)
        bindings = (approval_id, backup_id, manifest_hash, request_hash)
        if any(value is not None for value in bindings) and not all(value is not None for value in bindings):
            raise AdapterError("invalid_journal_binding", "privileged journal binding must be complete")
        if manifest_hash is not None:
            _digest(manifest_hash)
            _digest(request_hash)  # type: ignore[arg-type]
        path = self._path(operation_id)
        if path.exists():
            raise AdapterError("operation_exists", "operation journal already exists")
        now = utc_now()
        journal = OperationJournal(operation_id, "1.1", plan_id, host_id, change_set_hash, approval_id, backup_id, manifest_hash, request_hash, None, JournalStatus.APPLYING, targets, now, now, "")
        return self._write(replace(journal, journal_hash=_hash(journal)))

    def update(self, operation_id: str, status: JournalStatus) -> OperationJournal:
        current = self.load(operation_id)
        if status not in _TRANSITIONS[current.status]:
            raise AdapterError("invalid_journal_transition", "operation journal transition is not allowed")
        updated = replace(current, status=status, updated_at=utc_now(), journal_hash="")
        return self._write(replace(updated, journal_hash=_hash(updated)))

    def bind_rollback(self, operation_id: str, request_hash: str) -> OperationJournal:
        current = self.load(operation_id)
        if current.status is not JournalStatus.ROLLING_BACK or current.rollback_request_hash is not None:
            raise AdapterError("invalid_journal_transition", "rollback request cannot be bound in the current state")
        _digest(request_hash)
        updated = replace(current, rollback_request_hash=request_hash, updated_at=utc_now(), journal_hash="")
        return self._write(replace(updated, journal_hash=_hash(updated)))

    def load(self, operation_id: str) -> OperationJournal:
        path = self._path(operation_id)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise AdapterError("journal_not_found", "operation journal is missing or unsafe")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            journal = _decode(value)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise AdapterError("invalid_journal", "operation journal is malformed") from error
        if journal.operation_id != operation_id or _hash(replace(journal, journal_hash="")) != journal.journal_hash:
            raise AdapterError("invalid_journal", "operation journal integrity check failed")
        if _bytes(journal) != path.read_bytes():
            raise AdapterError("invalid_journal", "operation journal is not canonical")
        return journal

    def reconcile(self, operation_id: str) -> tuple[ReconciliationResult, ...]:
        journal = self.load(operation_id)
        results: list[ReconciliationResult] = []
        for item in journal.targets:
            target = self._target(item.target)
            if target.is_symlink() or (target.exists() and not target.is_file()):
                results.append(ReconciliationResult(item.target, ReconciliationState.UNKNOWN, None))
                continue
            actual = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
            if actual == item.before_hash:
                state = ReconciliationState.UNAPPLIED
            elif actual == item.after_hash:
                state = ReconciliationState.APPLIED
            else:
                state = ReconciliationState.UNKNOWN
            results.append(ReconciliationResult(item.target, state, actual))
        return tuple(results)

    def _write(self, journal: OperationJournal) -> OperationJournal:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        _atomic_write(self._path(journal.operation_id), _bytes(journal), 0o600)
        return journal

    def _path(self, operation_id: str) -> Path:
        return self.root / f"{_component(operation_id)}.json"

    def _target(self, target_text: str) -> Path:
        target = Path(target_text)
        if not target.is_absolute():
            raise AdapterError("invalid_target", "journal target must be absolute")
        parent = target.parent.resolve()
        if not any(_within(parent, root) for root in self.allowed_roots):
            raise AdapterError("target_not_allowed", "journal target is outside allowed roots")
        return parent / target.name


@dataclass(frozen=True, slots=True)
class RemoteJournalReconciler:
    """Reconcile an interrupted SSH operation without retrying any mutation."""

    journals: LocalOperationJournal
    remote_journal: object

    def reconcile(
        self,
        operation_id: str,
        manifest: BackupManifest,
        host: HostPort,
        cancellation: CancellationToken,
    ) -> tuple[ReconciliationResult, ...]:
        if cancellation.cancelled:
            raise OperationCancelled("remote reconciliation cancelled")
        journal = self.journals.load(operation_id)
        if (
            not manifest.complete
            or manifest.manifest_hash
            != _manifest_hash(replace(manifest, manifest_hash=""))
            or journal.host_id != manifest.host_id
            or journal.plan_id != manifest.plan_id
            or journal.change_set_hash != manifest.change_set_hash
            or journal.backup_id != manifest.backup_id
            or journal.manifest_hash != manifest.manifest_hash
        ):
            raise AdapterError(
                "recovery_binding_mismatch",
                "journal and backup manifest do not describe the same operation",
            )
        try:
            from .remote_journal import decode_remote_journal_evidence, validate_evidence_binding
            evidence_content = self.remote_journal.load_journal_evidence(
                operation_id, journal.request_hash, cancellation
            )
            evidence = decode_remote_journal_evidence(evidence_content)
            validate_evidence_binding(evidence, journal, manifest.host_fingerprint)
        except OperationCancelled:
            raise
        except (AdapterError, OSError, ValueError) as error:
            raise AdapterError(
                "remote_journal_unverified",
                "remote root journal could not be verified safely",
            ) from error
        try:
            identity = host.identify(cancellation)
        except OperationCancelled:
            raise
        except (AdapterError, OSError, ValueError) as error:
            raise AdapterError(
                "remote_reconciliation_failed",
                "remote host identity could not be observed safely",
            ) from error
        if (
            identity.host_id != journal.host_id
            or manifest.host_fingerprint is None
            or identity.fingerprint != manifest.host_fingerprint
        ):
            raise AdapterError(
                "recovery_host_mismatch",
                "reconnected SSH host identity does not match the backup",
            )
        results: list[ReconciliationResult] = []
        try:
            for item in journal.targets:
                if cancellation.cancelled:
                    raise OperationCancelled("remote reconciliation cancelled")
                observed = host.stat(item.target, cancellation)
                actual = observed.sha256 if observed.exists else None
                if (
                    observed.path != item.target
                    or observed.is_symlink
                    or (observed.exists and actual is None)
                ):
                    state = ReconciliationState.UNKNOWN
                elif actual == item.before_hash:
                    state = ReconciliationState.UNAPPLIED
                elif actual == item.after_hash:
                    state = ReconciliationState.APPLIED
                else:
                    state = ReconciliationState.UNKNOWN
                results.append(ReconciliationResult(item.target, state, actual))
        except OperationCancelled:
            raise
        except (AdapterError, OSError, ValueError) as error:
            raise AdapterError(
                "remote_reconciliation_failed",
                "remote state could not be observed safely",
            ) from error
        return tuple(results)


def _hash(journal: OperationJournal) -> str:
    return hashlib.sha256(_bytes(replace(journal, journal_hash=""))).hexdigest()


def _bytes(journal: OperationJournal) -> bytes:
    return json.dumps(to_primitive(journal), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode(value: object) -> OperationJournal:
    if not isinstance(value, dict) or value.get("schema_version") != "1.1":
        raise ValueError("unsupported journal schema")
    targets_value = value["targets"]
    if not isinstance(targets_value, list):
        raise ValueError("targets must be a list")
    targets = tuple(JournalTarget(_text(item, "target"), _optional_digest(item, "before_hash"), _required_digest(item, "after_hash")) for item in targets_value)
    journal = OperationJournal(
        operation_id=_text(value, "operation_id"),
        schema_version="1.1",
        plan_id=_text(value, "plan_id"),
        host_id=_text(value, "host_id"),
        change_set_hash=_text(value, "change_set_hash"),
        approval_id=_optional_text(value, "approval_id"),
        backup_id=_optional_text(value, "backup_id"),
        manifest_hash=_optional_digest(value, "manifest_hash"),
        request_hash=_optional_digest(value, "request_hash"),
        rollback_request_hash=_optional_digest(value, "rollback_request_hash"),
        status=JournalStatus(_text(value, "status")),
        targets=targets,
        created_at=_time(value, "created_at"),
        updated_at=_time(value, "updated_at"),
        journal_hash=_required_digest(value, "journal_hash"),
    )
    bindings = (journal.approval_id, journal.backup_id, journal.manifest_hash, journal.request_hash)
    if any(item is not None for item in bindings) and not all(item is not None for item in bindings):
        raise ValueError("incomplete privileged journal binding")
    return journal


def _text(value: object, key: str) -> str:
    if not isinstance(value, dict) or not isinstance(value.get(key), str) or not value[key]:
        raise ValueError(f"invalid {key}")
    return value[key]  # type: ignore[return-value]


def _time(value: dict[str, object], key: str) -> datetime:
    result = datetime.fromisoformat(_text(value, key))
    if result.tzinfo is None:
        raise ValueError("journal timestamps require timezone")
    return result


def _required_digest(value: object, key: str) -> str:
    return _digest(_text(value, key))


def _optional_digest(value: object, key: str) -> str | None:
    if not isinstance(value, dict):
        raise ValueError("invalid target")
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str):
        raise ValueError(f"invalid {key}")
    return _digest(item)


def _optional_text(value: object, key: str) -> str | None:
    if not isinstance(value, dict):
        raise ValueError("invalid journal")
    item = value.get(key)
    if item is not None and (not isinstance(item, str) or not item):
        raise ValueError(f"invalid {key}")
    return item


def _digest(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("invalid sha256 digest")
    return value


def _component(value: str) -> str:
    if not value or Path(value).name != value or value in {".", ".."}:
        raise AdapterError("invalid_operation_id", "operation ID must be a path component")
    return value
