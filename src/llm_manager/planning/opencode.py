from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from llm_manager.application.errors import AdapterError
from llm_manager.domain.enums import ChangeOperation, PlanStatus
from llm_manager.domain.models import Change, ChangeSet, DiagnosticReport, Recommendation

_ALLOWED_PATH = re.compile(
    r"(?:model|small_model|compaction\.(?:auto|prune|tail_turns|preserve_recent_tokens|reserved)|"
    r"provider\.[^.]+\.options\.(?:baseURL|timeout|headerTimeout|chunkTimeout)|"
    r"provider\.[^.]+\.models\.[^.]+\.limit\.context)"
)


@dataclass(frozen=True, slots=True)
class ConfigSnapshot:
    path: str
    content: str
    sha256: str

    @classmethod
    def capture(cls, path: str, content: str) -> "ConfigSnapshot":
        return cls(path, content, hashlib.sha256(content.encode("utf-8")).hexdigest())


@dataclass(frozen=True, slots=True)
class ScalarSpan:
    start: int
    end: int
    value: str | int | float | bool | None


@dataclass(slots=True)
class OpenCodeChangePlanner:
    supported_version: str = "1.18.25"

    def plan(
        self,
        report: DiagnosticReport,
        recommendations: tuple[Recommendation, ...],
        snapshot: ConfigSnapshot,
    ) -> ChangeSet:
        info = report.opencode
        if info is None or info.version != self.supported_version:
            raise AdapterError("unsupported_version", "OpenCode version is not change-enabled")
        if info.active_config != snapshot.path:
            raise AdapterError("source_conflict", "snapshot is not the active OpenCode config")
        if info.parse_warnings:
            raise AdapterError("parse_failed", "OpenCode config has parse warnings")
        spans = locate_scalar_spans(snapshot.content)
        changes: list[Change] = []
        for recommendation in sorted(recommendations, key=lambda item: item.recommendation_id):
            if not recommendation.actionable or recommendation.target != snapshot.path:
                continue
            path = recommendation.setting_key
            if not _ALLOWED_PATH.fullmatch(path):
                raise AdapterError("setting_not_allowed", f"setting is not allowlisted: {path}")
            span = spans.get(path)
            if span is None:
                raise AdapterError("source_conflict", f"existing scalar was not found: {path}")
            if span.value != recommendation.current_value:
                raise AdapterError("source_conflict", f"current scalar differs from recommendation: {path}")
            if type(span.value) is not type(recommendation.current_value):
                raise AdapterError("source_conflict", f"current scalar type differs from recommendation: {path}")
            _validate_value(path, recommendation.recommended_value)
            replacement = _encode_scalar(recommendation.recommended_value)
            changes.append(
                Change(
                    change_id=f"opencode:{recommendation.recommendation_id}",
                    target=snapshot.path,
                    operation=ChangeOperation.REPLACE_FILE,
                    before=span.value,
                    after=recommendation.recommended_value,
                    before_hash=snapshot.sha256,
                    diff=f"{path}: {_encode_scalar(span.value)} -> {replacement}",
                    requires_root=False,
                    requires_restart=False,
                    rollback_operation=ChangeOperation.REPLACE_FILE,
                    validation_checks=("opencode.config.parse", "opencode.setting.value"),
                    source_span=(span.start, span.end),
                    replacement_text=replacement,
                )
            )
        content_hash = _change_set_hash(report.host.host_id, changes)
        return ChangeSet(
            change_set_id=f"opencode:{report.report_id}:{content_hash[:12]}",
            host_id=report.host.host_id,
            changes=tuple(changes),
            content_hash=content_hash,
            status=PlanStatus.DRAFT,
        )


def locate_scalar_spans(content: str) -> dict[str, ScalarSpan]:
    return _JsoncSpanParser(content).parse()


class _JsoncSpanParser:
    def __init__(self, content: str) -> None:
        self.content = content
        self.position = 0
        self.spans: dict[str, ScalarSpan] = {}

    def parse(self) -> dict[str, ScalarSpan]:
        self._skip()
        self._object(())
        self._skip()
        if self.position != len(self.content):
            raise AdapterError("parse_failed", "unexpected content after JSONC root")
        return self.spans

    def _object(self, path: tuple[str, ...]) -> None:
        self._expect("{")
        self._skip()
        if self._take("}"):
            return
        while True:
            key, _, _ = self._string()
            self._skip()
            self._expect(":")
            self._value(path + (key,))
            self._skip()
            if self._take("}"):
                return
            self._expect(",")
            self._skip()
            if self._take("}"):
                return

    def _array(self, path: tuple[str, ...]) -> None:
        self._expect("[")
        self._skip()
        index = 0
        if self._take("]"):
            return
        while True:
            self._value(path + (f"[{index}]",))
            index += 1
            self._skip()
            if self._take("]"):
                return
            self._expect(",")
            self._skip()
            if self._take("]"):
                return

    def _value(self, path: tuple[str, ...]) -> None:
        self._skip()
        if self._peek() == "{":
            self._object(path)
            return
        if self._peek() == "[":
            self._array(path)
            return
        start = self.position
        if self._peek() == '"':
            value, _, end = self._string()
        else:
            while self.position < len(self.content) and self.content[self.position] not in ",]} \t\r\n/":
                self.position += 1
            end = self.position
            token = self.content[start:end]
            try:
                value = json.loads(token)
            except json.JSONDecodeError as error:
                raise AdapterError("parse_failed", "invalid JSONC scalar") from error
        self.spans[_path(path)] = ScalarSpan(start, end, value)

    def _string(self) -> tuple[str, int, int]:
        start = self.position
        self._expect('"')
        escaped = False
        while self.position < len(self.content):
            char = self.content[self.position]
            self.position += 1
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                raw = self.content[start:self.position]
                return json.loads(raw), start, self.position
        raise AdapterError("parse_failed", "unterminated JSONC string")

    def _skip(self) -> None:
        while self.position < len(self.content):
            if self.content[self.position].isspace():
                self.position += 1
            elif self.content.startswith("//", self.position):
                newline = self.content.find("\n", self.position + 2)
                self.position = len(self.content) if newline < 0 else newline + 1
            elif self.content.startswith("/*", self.position):
                end = self.content.find("*/", self.position + 2)
                if end < 0:
                    raise AdapterError("parse_failed", "unterminated JSONC comment")
                self.position = end + 2
            else:
                return

    def _expect(self, value: str) -> None:
        self._skip()
        if not self.content.startswith(value, self.position):
            raise AdapterError("parse_failed", f"expected {value}")
        self.position += len(value)

    def _take(self, value: str) -> bool:
        if self.content.startswith(value, self.position):
            self.position += len(value)
            return True
        return False

    def _peek(self) -> str:
        return self.content[self.position] if self.position < len(self.content) else ""


def _path(parts: tuple[str, ...]) -> str:
    result = ""
    for part in parts:
        result += part if part.startswith("[") else ("." if result else "") + part
    return result


def _encode_scalar(value: object) -> str:
    if not isinstance(value, (str, int, float, bool, type(None))):
        raise AdapterError("invalid_recommendation", "replacement must be a JSON scalar")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _validate_value(path: str, value: object) -> None:
    if path in {"compaction.auto", "compaction.prune"}:
        if type(value) is not bool:
            raise AdapterError("invalid_recommendation", f"{path} must be boolean")
        return
    if path in {
        "compaction.tail_turns",
        "compaction.preserve_recent_tokens",
        "compaction.reserved",
    }:
        if type(value) is not int or value < 0:
            raise AdapterError("invalid_recommendation", f"{path} must be a non-negative integer")
        return
    if path in {"model", "small_model"}:
        if not isinstance(value, str) or "/" not in value or not value.strip():
            raise AdapterError("invalid_recommendation", f"{path} must be a provider/model string")
        return
    if path.endswith(".options.baseURL"):
        if not isinstance(value, str):
            raise AdapterError("invalid_recommendation", "baseURL must be a string")
        parsed = urlsplit(value)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise AdapterError("invalid_recommendation", "baseURL must be a credential-free loopback HTTP URL")
        return
    if path.endswith((".options.timeout", ".options.headerTimeout")):
        if value is not False and (type(value) is not int or value <= 0):
            raise AdapterError("invalid_recommendation", f"{path} must be positive milliseconds or false")
        return
    if path.endswith(".options.chunkTimeout") or path.endswith(".limit.context"):
        if type(value) is not int or value <= 0:
            raise AdapterError("invalid_recommendation", f"{path} must be a positive integer")
        return
    raise AdapterError("setting_not_allowed", f"setting is not allowlisted: {path}")


def _change_set_hash(host_id: str, changes: list[Change]) -> str:
    payload = [
        (change.change_id, change.target, change.before_hash, change.source_span, change.replacement_text)
        for change in changes
    ]
    encoded = json.dumps((host_id, payload), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
