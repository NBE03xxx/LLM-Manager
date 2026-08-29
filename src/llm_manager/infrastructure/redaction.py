from __future__ import annotations

import re
from collections.abc import Iterable

REDACTED = "<redacted>"
_SECRET_KEY = re.compile(
    r"(?i)(authorization|api[-_]?key|token|password|secret|credential|auth[-_]?token)"
)
_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|api[-_]?key|token|password|secret|credential|auth[-_]?token)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_URL_USERINFO = re.compile(r"(?P<scheme>https?://)[^/@\s]+@")


def redact_text(value: str) -> str:
    value = _BEARER.sub(f"Bearer {REDACTED}", value)
    value = _ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", value)
    return _URL_USERINFO.sub(lambda match: f"{match.group('scheme')}{REDACTED}@", value)


def redact_argv(argv: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    hide_next = False
    for item in argv:
        if hide_next:
            result.append(REDACTED)
            hide_next = False
            continue
        result.append(redact_text(item))
        key = item.lstrip("-").split("=", 1)[0]
        hide_next = "=" not in item and bool(_SECRET_KEY.fullmatch(key))
    return tuple(result)


def redact_environment(items: Iterable[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    return tuple((key, REDACTED if _SECRET_KEY.search(key) else redact_text(value)) for key, value in items)
