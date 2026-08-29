from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.domain.models import utc_now
from llm_manager.domain.serialization import to_primitive

from .backup import _atomic_write
from .redaction import REDACTED, redact_text

_SECRET_KEY = re.compile(r"(?i)(authorization|api[-_]?key|token|password|secret|credential|private[-_]?key)")
_FORBIDDEN_KEY = re.compile(r"(?i)(content|raw[-_]?config|unmasked[-_]?diff|file[-_]?body)")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    sequence: int
    schema_version: str
    event_type: str
    correlation_id: str
    fields: tuple[tuple[str, str | int | float | bool | None], ...]
    created_at: datetime
    previous_hash: str | None
    event_hash: str


class LocalAuditLog:
    """Append-only, redacted audit events protected by a persisted hash chain."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def append(self, event_type: str, correlation_id: str, fields: tuple[tuple[str, object], ...]) -> None:
        if not event_type.strip() or not correlation_id.strip():
            raise AdapterError("invalid_audit_event", "event type and correlation ID are required")
        existing = self.read_all()
        sequence = len(existing) + 1
        previous_hash = existing[-1].event_hash if existing else None
        event = AuditEvent(
            sequence=sequence,
            schema_version="1.0",
            event_type=event_type,
            correlation_id=redact_text(correlation_id),
            fields=_sanitize(fields),
            created_at=utc_now(),
            previous_hash=previous_hash,
            event_hash="",
        )
        event = replace(event, event_hash=_hash(event))
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        _atomic_write(self.root / f"{sequence:020d}.json", _bytes(event), 0o600)
        _atomic_write(self.root / "HEAD", f"{sequence} {event.event_hash}\n".encode("ascii"), 0o600)

    def read_all(self) -> tuple[AuditEvent, ...]:
        if not self.root.exists():
            return ()
        if self.root.is_symlink() or not self.root.is_dir():
            raise AdapterError("invalid_audit_log", "audit directory is unsafe")
        files = sorted(self.root.glob("[0-9]" * 20 + ".json"))
        events: list[AuditEvent] = []
        previous_hash: str | None = None
        for expected, path in enumerate(files, start=1):
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
                raise AdapterError("invalid_audit_log", "audit event file is unsafe")
            try:
                event = _decode(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                raise AdapterError("invalid_audit_log", "audit event is malformed") from error
            if (
                event.sequence != expected
                or path.name != f"{expected:020d}.json"
                or event.previous_hash != previous_hash
                or event.event_hash != _hash(replace(event, event_hash=""))
                or path.read_bytes() != _bytes(event)
            ):
                raise AdapterError("invalid_audit_log", "audit hash chain is invalid")
            events.append(event)
            previous_hash = event.event_hash
        head = self.root / "HEAD"
        if not events and not head.exists():
            return ()
        if head.is_symlink() or not head.is_file():
            raise AdapterError("invalid_audit_log", "audit HEAD is missing or unsafe")
        expected_head = f"{len(events)} {previous_hash}\n"
        if head.read_text(encoding="ascii") != expected_head:
            raise AdapterError("invalid_audit_log", "audit HEAD does not match the event chain")
        return tuple(events)


def _sanitize(fields: tuple[tuple[str, object], ...]) -> tuple[tuple[str, str | int | float | bool | None], ...]:
    result: list[tuple[str, str | int | float | bool | None]] = []
    seen: set[str] = set()
    for key, value in fields:
        if not isinstance(key, str) or not key or key in seen:
            raise AdapterError("invalid_audit_event", "audit field names must be unique non-empty text")
        seen.add(key)
        if _FORBIDDEN_KEY.search(key):
            raise AdapterError("forbidden_audit_field", "raw content and diffs must not be audited")
        if _SECRET_KEY.search(key):
            sanitized: str | int | float | bool | None = REDACTED
        elif isinstance(value, str):
            sanitized = redact_text(value)
        elif value is None or type(value) in {bool, int, float}:
            sanitized = value  # type: ignore[assignment]
        else:
            raise AdapterError("invalid_audit_event", "audit values must be JSON scalars")
        result.append((key, sanitized))
    return tuple(result)


def _hash(event: AuditEvent) -> str:
    return hashlib.sha256(_bytes(replace(event, event_hash=""))).hexdigest()


def _bytes(event: AuditEvent) -> bytes:
    return json.dumps(to_primitive(event), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode(value: object) -> AuditEvent:
    if not isinstance(value, dict) or value.get("schema_version") != "1.0":
        raise ValueError("unsupported audit schema")
    raw_fields = value["fields"]
    if not isinstance(raw_fields, list):
        raise ValueError("audit fields must be a list")
    fields: list[tuple[str, str | int | float | bool | None]] = []
    for item in raw_fields:
        if not isinstance(item, list) or len(item) != 2 or not isinstance(item[0], str):
            raise ValueError("invalid audit field")
        field_value = item[1]
        if field_value is not None and type(field_value) not in {str, bool, int, float}:
            raise ValueError("invalid audit value")
        fields.append((item[0], field_value))
    created_at = datetime.fromisoformat(_text(value, "created_at"))
    if created_at.tzinfo is None:
        raise ValueError("audit timestamp requires timezone")
    sequence = value["sequence"]
    if type(sequence) is not int or sequence <= 0:
        raise ValueError("invalid audit sequence")
    previous = value["previous_hash"]
    if previous is not None:
        _digest(previous)
    return AuditEvent(sequence, "1.0", _text(value, "event_type"), _text(value, "correlation_id"), tuple(fields), created_at, previous, _digest(_text(value, "event_hash")))


def _text(value: dict[str, object], key: str) -> str:
    item = value[key]
    if not isinstance(item, str) or not item:
        raise ValueError(f"invalid {key}")
    return item


def _digest(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("invalid hash")
    return value
