from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass

from llm_manager.application.errors import AdapterError
from llm_manager.domain.enums import ChangeOperation, PlanStatus
from llm_manager.domain.models import Change, ChangeSet, DiagnosticReport, Recommendation

DROP_IN_PATH = "/etc/systemd/system/ollama.service.d/90-llm-manager.conf"
_KEYS = frozenset(
    {
        "OLLAMA_HOST",
        "OLLAMA_CONTEXT_LENGTH",
        "OLLAMA_KEEP_ALIVE",
        "OLLAMA_MAX_LOADED_MODELS",
        "OLLAMA_NUM_PARALLEL",
        "OLLAMA_MAX_QUEUE",
        "OLLAMA_FLASH_ATTENTION",
        "OLLAMA_KV_CACHE_TYPE",
    }
)


@dataclass(frozen=True, slots=True)
class OllamaSettingPolicy:
    numeric_bounds: tuple[tuple[str, int, int], ...] = ()

    def bounds_for(self, key: str) -> tuple[int, int] | None:
        return next(((minimum, maximum) for name, minimum, maximum in self.numeric_bounds if name == key), None)


@dataclass(frozen=True, slots=True)
class OllamaDropInPlanner:
    policy: OllamaSettingPolicy = OllamaSettingPolicy()
    supported_version: str = "0.33.2"

    def plan(
        self,
        report: DiagnosticReport,
        recommendations: tuple[Recommendation, ...],
        existing_content: str | None,
    ) -> ChangeSet:
        info = report.ollama
        if info is None or info.version != self.supported_version:
            raise AdapterError("unsupported_version", "Ollama version is not change-enabled")
        if info.service is None or info.service.unit != "ollama.service" or info.service.load_state != "loaded":
            raise AdapterError("unsupported_service", "supported system Ollama unit was not observed")
        selected = [
            item
            for item in sorted(recommendations, key=lambda value: value.setting_key)
            if item.actionable and item.target == "ollama.systemd"
        ]
        settings: list[tuple[str, str]] = []
        for item in selected:
            if item.setting_key not in _KEYS:
                raise AdapterError("setting_not_allowed", f"setting is not allowlisted: {item.setting_key}")
            settings.append((item.setting_key, self._validate(item.setting_key, item.recommended_value)))
        if not settings:
            changes: tuple[Change, ...] = ()
        else:
            rendered = render_drop_in(settings)
            before_hash = (
                hashlib.sha256(existing_content.encode("utf-8")).hexdigest()
                if existing_content is not None
                else None
            )
            operation = ChangeOperation.REPLACE_FILE if existing_content is not None else ChangeOperation.CREATE_FILE
            rollback = (
                ChangeOperation.REPLACE_FILE
                if existing_content is not None
                else ChangeOperation.REMOVE_CREATED_FILE
            )
            changes = (
                Change(
                    change_id=f"ollama:drop-in:{report.report_id}",
                    target=DROP_IN_PATH,
                    operation=operation,
                    before="exists" if existing_content is not None else "absent",
                    after=tuple(settings),
                    before_hash=before_hash,
                    diff="\n".join(f"{key}: <current> -> {value}" for key, value in settings),
                    requires_root=True,
                    requires_restart=True,
                    rollback_operation=rollback,
                    validation_checks=(
                        "systemd.daemon_reload",
                        "ollama.service.active",
                        "ollama.environment.effective",
                        "ollama.api.connectivity",
                    ),
                    source_span=(0, len(existing_content)) if existing_content is not None else None,
                    replacement_text=rendered,
                ),
            )
        digest = _hash(report.host.host_id, changes)
        return ChangeSet(
            change_set_id=f"ollama:{report.report_id}:{digest[:12]}",
            host_id=report.host.host_id,
            changes=changes,
            content_hash=digest,
            status=PlanStatus.DRAFT,
            affected_services=("ollama.service",) if changes else (),
        )

    def _validate(self, key: str, value: object) -> str:
        if key == "OLLAMA_HOST":
            if not isinstance(value, str):
                raise AdapterError("invalid_recommendation", "OLLAMA_HOST must be a string")
            host, separator, port_text = value.rpartition(":")
            host = host.strip("[]")
            try:
                address = ipaddress.ip_address(host)
                loopback = address.is_loopback
            except ValueError:
                loopback = host == "localhost"
            if not separator or not loopback or not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
                raise AdapterError("invalid_recommendation", "OLLAMA_HOST must be loopback with a valid port")
            return value
        if key in {"OLLAMA_FLASH_ATTENTION"}:
            if not isinstance(value, (str, int, bool)) or value not in {"0", "1", 0, 1, False, True}:
                raise AdapterError("invalid_recommendation", f"invalid {key}")
            return "1" if value in {"1", 1, True} else "0"
        if key == "OLLAMA_KV_CACHE_TYPE":
            if value not in {"f16", "q8_0", "q4_0"}:
                raise AdapterError("invalid_recommendation", "invalid OLLAMA_KV_CACHE_TYPE")
            return str(value)
        if key == "OLLAMA_KEEP_ALIVE":
            if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9]\d*)(?:ms|s|m|h)?", value):
                raise AdapterError("invalid_recommendation", "OLLAMA_KEEP_ALIVE must be a bounded duration")
            return value
        bounds = self.policy.bounds_for(key)
        if bounds is None:
            raise AdapterError("unverified_threshold", f"no verified bounds configured for {key}")
        if type(value) is not int or not bounds[0] <= value <= bounds[1]:
            raise AdapterError("invalid_recommendation", f"{key} is outside verified bounds")
        return str(value)


def render_drop_in(settings: list[tuple[str, str]]) -> str:
    lines = ["[Service]"]
    for key, value in settings:
        if any(character in value for character in "\n\r\x00\""):
            raise AdapterError("invalid_recommendation", f"unsafe systemd value for {key}")
        lines.append(f'Environment="{key}={value}"')
    return "\n".join(lines) + "\n"


def _hash(host_id: str, changes: tuple[Change, ...]) -> str:
    payload = [
        (item.change_id, item.target, item.operation.value, item.before_hash, item.replacement_text)
        for item in changes
    ]
    encoded = json.dumps((host_id, payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
