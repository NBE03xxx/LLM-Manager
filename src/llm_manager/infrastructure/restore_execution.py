from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.application.restore_preflight import PreparedRestoreAuthorization
from llm_manager.domain.models import utc_now
from llm_manager.domain.serialization import to_primitive

from .backup import _atomic_write
from .local_restore import LocalRestoreResult, SingleTargetLocalRestoreExecutor


class RestoreExecutionState(StrEnum):
    COMMITTED = "committed"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RestoreExecutionAttempt:
    schema_version: str
    authorization_hash: str
    host_id: str
    backup_id: str
    manifest_hash: str
    preview_hash: str
    approval_id: str
    actor: str
    target: str
    started_at: datetime
    attempt_hash: str = ""

    def with_hash(self) -> "RestoreExecutionAttempt":
        value = replace(self, attempt_hash="")
        return replace(value, attempt_hash=hashlib.sha256(_canonical(value)).hexdigest())


@dataclass(frozen=True, slots=True)
class RestoreExecutionEvidence:
    schema_version: str
    attempt_hash: str
    authorization_hash: str
    host_id: str
    backup_id: str
    manifest_hash: str
    target: str
    state: RestoreExecutionState
    completed_at: datetime
    error_code: str | None
    evidence_hash: str = ""

    def with_hash(self) -> "RestoreExecutionEvidence":
        value = replace(self, evidence_hash="")
        return replace(value, evidence_hash=hashlib.sha256(_canonical(value)).hexdigest())


class RestoreExecutionPersistenceError(AdapterError):
    def __init__(self, evidence: RestoreExecutionEvidence, cause_code: str) -> None:
        super().__init__(
            "restore_execution_persistence_failed",
            "restore may have changed the target but its result could not be persisted",
        )
        self.evidence = evidence
        self.cause_code = cause_code


@dataclass(frozen=True, slots=True)
class RestoreExecutionView:
    attempt: RestoreExecutionAttempt
    evidence: RestoreExecutionEvidence | None

    @property
    def state(self) -> RestoreExecutionState | str:
        return self.evidence.state if self.evidence is not None else "attempt_only"

    @property
    def requires_attention(self) -> bool:
        return self.evidence is None or self.evidence.state is not RestoreExecutionState.COMMITTED


class RestoreAuditPort(Protocol):
    def append(
        self, event_type: str, correlation_id: str,
        fields: tuple[tuple[str, object], ...],
    ) -> None: ...


class RestoreExecutionStore:
    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        if self.root == Path("/") or self.root.is_symlink():
            raise ValueError("unsafe restore execution root")

    def save_attempt(self, value: RestoreExecutionAttempt) -> RestoreExecutionAttempt:
        value = value.with_hash()
        path = self._path(value.authorization_hash, "attempt")
        self._prepare()
        if path.exists() or path.is_symlink():
            raise AdapterError("restore_authorization_consumed", "authorization was already consumed")
        _atomic_write(path, _canonical(value), 0o600)
        return self.load_attempt(value.authorization_hash)

    def save_evidence(self, value: RestoreExecutionEvidence) -> RestoreExecutionEvidence:
        value = value.with_hash()
        path = self._path(value.authorization_hash, "result")
        self._prepare()
        if path.exists() or path.is_symlink():
            raise AdapterError("restore_result_exists", "restore result is immutable")
        _atomic_write(path, _canonical(value), 0o600)
        return self.load_evidence(value.authorization_hash)

    def load_attempt(self, authorization_hash: str) -> RestoreExecutionAttempt:
        path = self._path(authorization_hash, "attempt")
        content = self._read(path)
        try:
            raw = json.loads(content.decode("utf-8"))
            value = RestoreExecutionAttempt(
                _text(raw, "schema_version"), _text(raw, "authorization_hash"),
                _text(raw, "host_id"), _text(raw, "backup_id"),
                _text(raw, "manifest_hash"), _text(raw, "preview_hash"),
                _text(raw, "approval_id"), _text(raw, "actor"),
                _text(raw, "target"), datetime.fromisoformat(_text(raw, "started_at")),
                _text(raw, "attempt_hash"),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise AdapterError("invalid_restore_attempt", "restore attempt is malformed") from error
        if (
            set(raw) != {
                "schema_version", "authorization_hash", "host_id", "backup_id",
                "manifest_hash", "preview_hash", "approval_id", "actor", "target",
                "started_at", "attempt_hash",
            }
            or value.schema_version != "1.0"
            or value.authorization_hash != authorization_hash
            or value.started_at.tzinfo is None
            or value.with_hash() != value
            or content != _canonical(value)
        ):
            raise AdapterError("invalid_restore_attempt", "restore attempt integrity failed")
        return value

    def load_evidence(self, authorization_hash: str) -> RestoreExecutionEvidence:
        path = self._path(authorization_hash, "result")
        content = self._read(path)
        try:
            raw = json.loads(content.decode("utf-8"))
            error_code = raw["error_code"]
            if error_code is not None and not isinstance(error_code, str):
                raise ValueError("invalid error code")
            value = RestoreExecutionEvidence(
                _text(raw, "schema_version"), _text(raw, "attempt_hash"),
                _text(raw, "authorization_hash"), _text(raw, "host_id"),
                _text(raw, "backup_id"), _text(raw, "manifest_hash"),
                _text(raw, "target"), RestoreExecutionState(_text(raw, "state")),
                datetime.fromisoformat(_text(raw, "completed_at")), error_code,
                _text(raw, "evidence_hash"),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise AdapterError("invalid_restore_evidence", "restore evidence is malformed") from error
        if (
            set(raw) != {
                "schema_version", "attempt_hash", "authorization_hash", "host_id",
                "backup_id", "manifest_hash", "target", "state", "completed_at",
                "error_code", "evidence_hash",
            }
            or value.schema_version != "1.0"
            or value.authorization_hash != authorization_hash
            or value.completed_at.tzinfo is None
            or (value.state is RestoreExecutionState.COMMITTED) != (value.error_code is None)
            or value.with_hash() != value
            or content != _canonical(value)
        ):
            raise AdapterError("invalid_restore_evidence", "restore evidence integrity failed")
        return value

    def list_strict(self) -> tuple[RestoreExecutionView, ...]:
        if not self.root.exists() and not self.root.is_symlink():
            return ()
        if self.root.is_symlink() or not self.root.is_dir():
            raise AdapterError("unsafe_restore_execution_store", "restore store is unsafe")
        metadata = self.root.stat(follow_symlinks=False)
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise AdapterError("unsafe_restore_execution_store", "restore store is unsafe")
        identities: dict[str, set[str]] = {}
        for path in self.root.iterdir():
            parts = path.name.split(".")
            if (
                path.is_symlink()
                or not path.is_file()
                or len(parts) != 3
                or parts[1] not in {"attempt", "result"}
                or parts[2] != "json"
            ):
                raise AdapterError("unsafe_restore_execution_store", "unknown restore entry")
            self._path(parts[0], parts[1])
            identities.setdefault(parts[0], set()).add(parts[1])
        views = []
        for identity, kinds in identities.items():
            if "attempt" not in kinds:
                raise AdapterError("invalid_restore_evidence", "result has no source attempt")
            attempt = self.load_attempt(identity)
            evidence = self.load_evidence(identity) if "result" in kinds else None
            if evidence is not None and (
                evidence.attempt_hash != attempt.attempt_hash
                or (
                    evidence.authorization_hash, evidence.host_id, evidence.backup_id,
                    evidence.manifest_hash, evidence.target,
                ) != (
                    attempt.authorization_hash, attempt.host_id, attempt.backup_id,
                    attempt.manifest_hash, attempt.target,
                )
            ):
                raise AdapterError("invalid_restore_evidence", "restore evidence binding changed")
            views.append(RestoreExecutionView(attempt, evidence))
        return tuple(sorted(views, key=lambda item: item.attempt.started_at, reverse=True))

    def _prepare(self) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        metadata = self.root.stat(follow_symlinks=False)
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise AdapterError("unsafe_restore_execution_store", "restore store is unsafe")

    def _read(self, path: Path) -> bytes:
        if not self.root.exists() or self.root.is_symlink() or not self.root.is_dir():
            raise AdapterError("restore_execution_not_found", "restore execution is missing")
        root_metadata = self.root.stat(follow_symlinks=False)
        if root_metadata.st_uid != os.getuid() or stat.S_IMODE(root_metadata.st_mode) != 0o700:
            raise AdapterError("unsafe_restore_execution_store", "restore store is unsafe")
        if path.is_symlink() or not path.is_file():
            raise AdapterError("restore_execution_not_found", "restore execution is missing")
        metadata = path.stat(follow_symlinks=False)
        if (
            metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > 1024 * 1024
        ):
            raise AdapterError("unsafe_restore_execution_store", "restore record is unsafe")
        return path.read_bytes()

    def _path(self, identity: str, kind: str) -> Path:
        if len(identity) != 64 or any(value not in "0123456789abcdef" for value in identity):
            raise AdapterError("invalid_restore_authorization", "authorization hash is invalid")
        return self.root / f"{identity}.{kind}.json"


@dataclass(slots=True)
class LocalRestoreCoordinator:
    executor: SingleTargetLocalRestoreExecutor
    store: RestoreExecutionStore
    audit: RestoreAuditPort

    def execute(
        self,
        authorization: PreparedRestoreAuthorization,
        cancellation: CancellationToken,
    ) -> RestoreExecutionEvidence:
        if authorization.with_hash() != authorization or len(authorization.targets) != 1:
            raise AdapterError("invalid_restore_authorization", "restore authorization is invalid")
        attempt = self.store.save_attempt(RestoreExecutionAttempt(
            "1.0", authorization.authorization_hash, authorization.host_id,
            authorization.backup_id, authorization.manifest_hash,
            authorization.preview_hash, authorization.approval_id, authorization.actor,
            authorization.targets[0], utc_now(),
        ))
        self.audit.append("restore.started", authorization.authorization_hash, (
            ("host_id", authorization.host_id), ("backup_id", authorization.backup_id),
            ("binding_hash", authorization.authorization_hash),
        ))
        try:
            result = self.executor.execute(authorization, cancellation)
        except (AdapterError, OSError, OperationCancelled) as error:
            evidence = self._evidence(
                attempt, RestoreExecutionState.FAILED,
                getattr(error, "code", type(error).__name__),
            )
            self._persist(evidence)
            raise
        evidence = self._evidence(attempt, RestoreExecutionState.COMMITTED, None)
        try:
            self.audit.append("restore.committed", authorization.authorization_hash, (
                ("host_id", result.host_id), ("backup_id", result.backup_id),
                ("binding_hash", result.authorization_hash),
            ))
        except (AdapterError, OSError) as error:
            evidence = replace(
                evidence, state=RestoreExecutionState.UNKNOWN,
                error_code=getattr(error, "code", type(error).__name__), evidence_hash="",
            ).with_hash()
            self._persist(evidence)
            raise RestoreExecutionPersistenceError(evidence, evidence.error_code or "audit_failed")
        return self._persist(evidence)

    def _persist(self, evidence: RestoreExecutionEvidence) -> RestoreExecutionEvidence:
        try:
            return self.store.save_evidence(evidence)
        except (AdapterError, OSError) as error:
            raise RestoreExecutionPersistenceError(
                evidence, getattr(error, "code", type(error).__name__)
            ) from error

    @staticmethod
    def _evidence(
        attempt: RestoreExecutionAttempt,
        state: RestoreExecutionState,
        error_code: str | None,
    ) -> RestoreExecutionEvidence:
        return RestoreExecutionEvidence(
            "1.0", attempt.attempt_hash, attempt.authorization_hash,
            attempt.host_id, attempt.backup_id, attempt.manifest_hash, attempt.target,
            state, utc_now(), error_code,
        ).with_hash()


def _canonical(value: object) -> bytes:
    return json.dumps(
        to_primitive(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _text(value: object, key: str) -> str:
    if not isinstance(value, dict):
        raise ValueError("restore record must be an object")
    item = value[key]
    if not isinstance(item, str) or not item:
        raise ValueError(f"invalid {key}")
    return item
