from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Protocol

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.serialization import to_primitive

from .journal import JournalStatus, JournalTarget, OperationJournal, _digest


MAX_REMOTE_JOURNAL_EVIDENCE_BYTES = 1024 * 1024


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
