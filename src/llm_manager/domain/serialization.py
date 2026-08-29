from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .errors import InvariantViolation

SCHEMA_MAJOR = 1


def to_primitive(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: to_primitive(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [to_primitive(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_primitive(item) for key, item in value.items()}
    return value


def make_envelope(kind: str, payload: object, schema_version: str = "1.0") -> dict[str, object]:
    validate_schema_version(schema_version)
    if not kind.strip():
        raise InvariantViolation("envelope kind must not be blank")
    return {"schema_version": schema_version, "kind": kind, "payload": to_primitive(payload)}


def validate_schema_version(schema_version: str) -> None:
    try:
        major_text, _minor_text = schema_version.split(".", 1)
        major = int(major_text)
    except (ValueError, AttributeError) as error:
        raise InvariantViolation("schema_version must be MAJOR.MINOR") from error
    if major != SCHEMA_MAJOR:
        raise InvariantViolation(f"unsupported schema major: {major}")
