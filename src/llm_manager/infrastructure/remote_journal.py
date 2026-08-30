from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.serialization import to_primitive

from .journal import JournalStatus, JournalTarget, OperationJournal, _digest


MAX_REMOTE_JOURNAL_EVIDENCE_BYTES = 1024 * 1024
REMOTE_JOURNAL_EVIDENCE_ROOT = Path("/var/lib/llm-manager/journals/evidence")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


@dataclass(frozen=True, slots=True)
class RemoteJournalEvidence:
    schema_version: str
    operation_id: str
    plan_id: str
    host_id: str
    host_fingerprint: str
    change_set_hash: str
    backup_id: str
    manifest_hash: str
    request_hash: str
    rollback_request_hash: str | None
    status: JournalStatus
    targets: tuple[JournalTarget, ...]
    remote_journal_hash: str
    evidence_hash: str = ""

    def with_hash(self) -> "RemoteJournalEvidence":
        value = replace(self, evidence_hash="")
        return replace(value, evidence_hash=hashlib.sha256(_bytes(value)).hexdigest())


class RemoteRootJournalPort(Protocol):
    """Fetch a fixed, redacted journal evidence result through the remote helper."""

    def load_journal_evidence(
        self,
        operation_id: str,
        request_hash: str,
        cancellation: CancellationToken,
    ) -> bytes: ...


class RemoteRootJournalEvidenceStore:
    """Read immutable, root-owned evidence from one fixed production directory."""

    def __init__(
        self,
        root: Path = REMOTE_JOURNAL_EVIDENCE_ROOT,
        *,
        sandbox: bool = False,
        effective_uid: int | None = None,
        owner_uid: int | None = None,
    ) -> None:
        self.root = root.absolute()
        uid = os.geteuid() if effective_uid is None else effective_uid
        self.owner_uid = (os.getuid() if sandbox else 0) if owner_uid is None else owner_uid
        self.owner_gid = os.getgid() if sandbox else 0
        if not sandbox and self.root != REMOTE_JOURNAL_EVIDENCE_ROOT:
            raise AdapterError("invalid_remote_journal_root", "remote journal root is fixed")
        if not sandbox and self.root.resolve(strict=False) != REMOTE_JOURNAL_EVIDENCE_ROOT:
            raise AdapterError("invalid_remote_journal_root", "remote journal root escaped")
        if not sandbox and uid != 0:
            raise AdapterError("root_required", "remote journal evidence requires root")
        if self.root == Path("/") or self.root.is_symlink():
            raise AdapterError("invalid_remote_journal_root", "remote journal root is unsafe")

    def load_journal_evidence(
        self,
        operation_id: str,
        request_hash: str,
        cancellation: CancellationToken,
    ) -> bytes:
        if cancellation.cancelled:
            from llm_manager.application.errors import OperationCancelled
            raise OperationCancelled("remote journal retrieval cancelled")
        if not _IDENTIFIER.fullmatch(operation_id):
            raise AdapterError("invalid_remote_journal_identity", "operation identity is invalid")
        _digest(request_hash)
        self._private_directory(self.root)
        path = self.root / f"{operation_id}.json"
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise AdapterError("unsafe_remote_journal", "remote journal evidence is unavailable") from error
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != self.owner_uid
                or metadata.st_gid != self.owner_gid
            ):
                raise AdapterError(
                    "unsafe_remote_journal", "remote journal evidence owner or mode is unsafe"
                )
            chunks: list[bytes] = []
            remaining = MAX_REMOTE_JOURNAL_EVIDENCE_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            content = b"".join(chunks)
        finally:
            os.close(descriptor)
        if len(content) > MAX_REMOTE_JOURNAL_EVIDENCE_BYTES:
            raise AdapterError("remote_journal_too_large", "remote journal evidence exceeds 1 MiB")
        evidence = decode_remote_journal_evidence(content)
        if evidence.operation_id != operation_id or evidence.request_hash != request_hash:
            raise AdapterError(
                "remote_journal_binding_mismatch", "remote journal evidence identity is invalid"
            )
        return content

    def _private_directory(self, path: Path) -> None:
        if path.is_symlink() or not path.is_dir():
            raise AdapterError("unsafe_remote_journal", "remote journal evidence path is unsafe")
        metadata = path.stat(follow_symlinks=False)
        if (
            metadata.st_uid != self.owner_uid
            or metadata.st_gid != self.owner_gid
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise AdapterError(
                "unsafe_remote_journal", "remote journal evidence owner or mode is unsafe"
            )


def encode_remote_journal_evidence(evidence: RemoteJournalEvidence) -> bytes:
    validate_remote_journal_evidence(evidence)
    content = _bytes(evidence)
    if len(content) > MAX_REMOTE_JOURNAL_EVIDENCE_BYTES:
        raise AdapterError("remote_journal_too_large", "remote journal evidence exceeds 1 MiB")
    return content


def decode_remote_journal_evidence(content: bytes) -> RemoteJournalEvidence:
    if len(content) > MAX_REMOTE_JOURNAL_EVIDENCE_BYTES:
        raise AdapterError("remote_journal_too_large", "remote journal evidence exceeds 1 MiB")
    try:
        evidence = _decode(json.loads(content.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise AdapterError("invalid_remote_journal", "remote journal evidence is malformed") from error
    if content != _bytes(evidence):
        raise AdapterError("invalid_remote_journal", "remote journal evidence is not canonical")
    validate_remote_journal_evidence(evidence)
    return evidence


def validate_remote_journal_evidence(evidence: RemoteJournalEvidence) -> None:
    if evidence.schema_version != "1.0" or not evidence.operation_id or not evidence.host_fingerprint:
        raise AdapterError("invalid_remote_journal", "remote journal evidence identity is invalid")
    for value in (
        evidence.manifest_hash, evidence.request_hash, evidence.remote_journal_hash,
        evidence.evidence_hash,
    ):
        _digest(value)
    if evidence.rollback_request_hash is not None:
        _digest(evidence.rollback_request_hash)
    expected = hashlib.sha256(_bytes(replace(evidence, evidence_hash=""))).hexdigest()
    if evidence.evidence_hash != expected or not evidence.targets:
        raise AdapterError("invalid_remote_journal", "remote journal evidence integrity is invalid")
    for target in evidence.targets:
        if not target.target:
            raise AdapterError("invalid_remote_journal", "remote journal target is invalid")
        _digest(target.after_hash)
        if target.before_hash is not None:
            _digest(target.before_hash)


def validate_evidence_binding(
    evidence: RemoteJournalEvidence,
    journal: OperationJournal,
    host_fingerprint: str,
) -> None:
    if (
        evidence.operation_id != journal.operation_id
        or evidence.plan_id != journal.plan_id
        or evidence.host_id != journal.host_id
        or evidence.host_fingerprint != host_fingerprint
        or evidence.change_set_hash != journal.change_set_hash
        or evidence.backup_id != journal.backup_id
        or evidence.manifest_hash != journal.manifest_hash
        or evidence.request_hash != journal.request_hash
        or evidence.rollback_request_hash != journal.rollback_request_hash
        or evidence.status != journal.status
        or evidence.targets != journal.targets
    ):
        raise AdapterError(
            "remote_journal_binding_mismatch",
            "remote root journal does not match the local recovery operation",
        )


def _bytes(evidence: RemoteJournalEvidence) -> bytes:
    return json.dumps(to_primitive(evidence), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode(value: object) -> RemoteJournalEvidence:
    expected = {
        "backup_id", "change_set_hash", "evidence_hash", "host_fingerprint", "host_id",
        "manifest_hash", "operation_id", "plan_id", "remote_journal_hash",
        "request_hash", "rollback_request_hash", "schema_version", "status", "targets",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("invalid evidence fields")
    strings = expected - {"rollback_request_hash", "targets"}
    if any(not isinstance(value[key], str) or not value[key] for key in strings):
        raise ValueError("invalid evidence strings")
    rollback = value["rollback_request_hash"]
    if rollback is not None and not isinstance(rollback, str):
        raise ValueError("invalid rollback request hash")
    targets = value["targets"]
    if not isinstance(targets, list):
        raise ValueError("invalid evidence targets")
    decoded_targets = []
    for item in targets:
        if not isinstance(item, dict) or set(item) != {"after_hash", "before_hash", "target"}:
            raise ValueError("invalid evidence target")
        if not isinstance(item["target"], str) or not isinstance(item["after_hash"], str):
            raise ValueError("invalid evidence target values")
        if item["before_hash"] is not None and not isinstance(item["before_hash"], str):
            raise ValueError("invalid evidence before hash")
        decoded_targets.append(JournalTarget(item["target"], item["before_hash"], item["after_hash"]))
    return RemoteJournalEvidence(
        value["schema_version"], value["operation_id"], value["plan_id"], value["host_id"],
        value["host_fingerprint"], value["change_set_hash"], value["backup_id"],
        value["manifest_hash"], value["request_hash"], rollback, JournalStatus(value["status"]),
        tuple(decoded_targets), value["remote_journal_hash"], value["evidence_hash"],
    )
