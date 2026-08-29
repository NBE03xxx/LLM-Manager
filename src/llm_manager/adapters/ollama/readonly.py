from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken, CommandRequest, HostPort
from llm_manager.domain.enums import ProbeStatus
from llm_manager.domain.models import (
    ChangeSet,
    DiagnosticReport,
    OllamaInfo,
    OllamaModelInfo,
    ServiceInfo,
    ValidationResult,
)
from llm_manager.infrastructure.redaction import redact_environment

_VERSION = re.compile(
    r"(?:(?:ollama|client)\s+)?version(?:\s+is)?\s+v?([0-9][^\s]*)", re.IGNORECASE
)


@dataclass(slots=True)
class OllamaReadOnlyAdapter:
    endpoint: str = "http://127.0.0.1:11434"
    timeout_ms: int = 3_000
    binary: str = "ollama"

    def __post_init__(self) -> None:
        parsed = urlsplit(self.endpoint)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("automatic Ollama inspection is restricted to a loopback HTTP endpoint")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Ollama endpoint must not contain credentials, query, or fragment")

    def inspect(self, host: HostPort, cancellation: CancellationToken) -> OllamaInfo:
        version_document = self._api(host, "/api/version", "ollama.api.version", cancellation)
        version = _string(version_document.get("version")) if version_document else None
        cli_detected = False
        if version is None:
            try:
                version_result = self._run(host, (self.binary, "--version"), "ollama.version", cancellation)
            except AdapterError:
                version_result = None
            if version_result is not None:
                version = parse_ollama_version(version_result.stdout + "\n" + version_result.stderr_redacted)
                cli_detected = version_result.exit_code != 127
        if version is None and not cli_detected:
            return OllamaInfo(installed=False, api_endpoint=self.endpoint)
        service_result = self._inspect_service(host, cancellation)
        service, service_output = service_result if service_result else (None, "")
        tags = self._api(host, "/api/tags", "ollama.tags", cancellation)
        running = self._api(host, "/api/ps", "ollama.ps", cancellation)
        connectivity = ProbeStatus.OK if tags is not None else ProbeStatus.UNAVAILABLE
        return OllamaInfo(
            installed=True,
            version=version,
            binary_path=self.binary,
            service=service,
            environment=redact_environment(parse_systemd_environment(service_output)),
            api_endpoint=self.endpoint,
            api_connectivity=connectivity,
            models=parse_models(tags or {}, loaded=False),
            loaded_models=parse_models(running or {}, loaded=True),
        )

    def _inspect_service(
        self, host: HostPort, cancellation: CancellationToken
    ) -> ServiceInfo | tuple[ServiceInfo, str] | None:
        result = self._run(
            host,
            (
                "systemctl",
                "show",
                "ollama.service",
                "--property=LoadState,ActiveState,SubState,UnitFileState,FragmentPath,DropInPaths,Environment",
                "--no-pager",
            ),
            "ollama.systemd",
            cancellation,
        )
        if result.exit_code != 0:
            return None
        values = parse_key_value_lines(result.stdout)
        service = ServiceInfo(
            unit="ollama.service",
            load_state=values.get("LoadState", "unknown"),
            active_state=values.get("ActiveState", "unknown"),
            sub_state=values.get("SubState", "unknown"),
            enabled=_enabled(values.get("UnitFileState")),
            fragment_path=values.get("FragmentPath") or None,
            drop_in_paths=tuple(values.get("DropInPaths", "").split()),
        )
        return service, result.stdout

    def _api(
        self, host: HostPort, path: str, correlation_id: str, cancellation: CancellationToken
    ) -> dict[str, object] | None:
        try:
            result = self._run(
                host,
                ("curl", "--silent", "--show-error", "--max-time", str(self.timeout_ms / 1000), self.endpoint + path),
                correlation_id,
                cancellation,
            )
        except (AdapterError, KeyError):
            return None
        if result.exit_code != 0 or result.timed_out:
            return None
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def _run(
        self, host: HostPort, argv: tuple[str, ...], correlation_id: str, cancellation: CancellationToken
    ):
        return host.execute_readonly(CommandRequest(argv, self.timeout_ms, correlation_id), cancellation)

    def validate_api(self, host: HostPort, cancellation: CancellationToken) -> tuple[ValidationResult, ...]:
        raise AdapterError("not_implemented", "validation belongs to Phase 4")

    def plan_setting_changes(
        self, report: DiagnosticReport, setting_values: tuple[tuple[str, object], ...]
    ) -> ChangeSet:
        raise AdapterError("not_implemented", "planning belongs to Phase 3")


def parse_ollama_version(content: str) -> str | None:
    match = _VERSION.search(content.strip())
    return match.group(1) if match else None


def parse_key_value_lines(content: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in content.splitlines() if "=" in line)


def parse_systemd_environment(service_output: str) -> tuple[tuple[str, str], ...]:
    raw = parse_key_value_lines(service_output).get("Environment", "")
    values: list[tuple[str, str]] = []
    for item in raw.split():
        if "=" in item:
            values.append(tuple(item.split("=", 1)))  # type: ignore[arg-type]
    return tuple(values)


def parse_models(document: dict[str, object], loaded: bool) -> tuple[OllamaModelInfo, ...]:
    key = "models"
    raw_models = document.get(key, [])
    if not isinstance(raw_models, list):
        return ()
    models: list[OllamaModelInfo] = []
    for raw in raw_models:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
            continue
        details = raw.get("details") if isinstance(raw.get("details"), dict) else {}
        models.append(
            OllamaModelInfo(
                name=raw["name"],
                digest=_string(raw.get("digest")),
                size_bytes=_integer(raw.get("size")),
                architecture=_string(details.get("family")),
                parameter_size=_string(details.get("parameter_size")),
                quantization=_string(details.get("quantization_level")),
                runtime_context=_integer(raw.get("context_length")),
                loaded=loaded,
                processor=_string(raw.get("processor")),
                gpu_memory_bytes=_integer(raw.get("size_vram")),
            )
        )
    return tuple(models)


def _enabled(value: str | None) -> bool | None:
    if value in {"enabled", "enabled-runtime"}:
        return True
    if value in {"disabled", "masked"}:
        return False
    return None


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
