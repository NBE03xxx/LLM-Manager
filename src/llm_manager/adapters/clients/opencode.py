from __future__ import annotations

import json
import re
from dataclasses import dataclass

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken, CommandRequest, HostPort
from llm_manager.domain.enums import Severity, ValidationStatus
from llm_manager.domain.models import ChangeSet, DiagnosticReport, LocalizedMessage, OpenCodeInfo, ValidationResult

_VERSION = re.compile(r"(?:opencode\s+)?v?([0-9]+\.[0-9]+\.[0-9]+(?:[-+][^\s]+)?)", re.IGNORECASE)
_CONTEXT_KEYS = frozenset({"context", "contextLength", "context_length", "compaction"})
_TIMEOUT_KEYS = frozenset({"timeout", "requestTimeout", "request_timeout"})


@dataclass(slots=True)
class OpenCodeReadOnlyAdapter:
    config_candidates: tuple[str, ...]
    timeout_ms: int = 3_000
    client_id: str = "opencode"
    binary: str = "opencode"

    def inspect(self, host: HostPort, cancellation: CancellationToken) -> OpenCodeInfo:
        result = host.execute_readonly(
            CommandRequest((self.binary, "--version"), self.timeout_ms, "opencode.version"), cancellation
        )
        if result.exit_code != 0:
            return OpenCodeInfo(installed=False, config_locations=self.config_candidates)
        version = parse_opencode_version(result.stdout)
        active, document, warnings = self._read_config(host, cancellation)
        provider, model, base_url = extract_connection(document)
        providers, models, base_urls = extract_available_connections(document)
        return OpenCodeInfo(
            installed=True,
            version=version,
            binary_path=self.binary,
            config_locations=self.config_candidates,
            active_config=active,
            provider=provider,
            model=model,
            base_url=base_url,
            available_providers=providers,
            available_models=models,
            base_urls=base_urls,
            context_settings=extract_settings(document, _CONTEXT_KEYS),
            timeout_settings=extract_settings(document, _TIMEOUT_KEYS),
            ollama_compatible=_ollama_compatible(provider, base_url, providers, base_urls),
            parse_warnings=warnings,
        )

    def _read_config(
        self, host: HostPort, cancellation: CancellationToken
    ) -> tuple[str | None, dict[str, object], tuple[str, ...]]:
        for candidate in self.config_candidates:
            if not host.stat(candidate, cancellation).exists:
                continue
            try:
                content = host.read_file(candidate, 2 * 1024 * 1024, cancellation).decode(
                    "utf-8", errors="strict"
                )
                parsed = parse_jsonc(content)
            except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
                return candidate, {}, ("opencode.config.parse_failed",)
            if not isinstance(parsed, dict):
                return candidate, {}, ("opencode.config.root_not_object",)
            return candidate, parsed, ()
        return None, {}, ()

    def validate(self, host: HostPort, cancellation: CancellationToken) -> tuple[ValidationResult, ...]:
        info = self.inspect(host, cancellation)
        checks = (
            ("opencode.installed", info.installed, "installed", "installed" if info.installed else "not_installed"),
            (
                "opencode.config.parse",
                info.active_config is not None and not info.parse_warnings,
                "valid",
                info.parse_warnings[0] if info.parse_warnings else ("valid" if info.active_config else "not_found"),
            ),
        )
        return tuple(
            ValidationResult(
                validation_id=check,
                scope="opencode",
                check=check,
                status=ValidationStatus.PASSED if passed else ValidationStatus.FAILED,
                expected=expected,
                actual=actual,
                severity=Severity.INFO if passed else Severity.HIGH,
                message=LocalizedMessage(f"validation.{check}.{'passed' if passed else 'failed'}"),
            )
            for check, passed, expected, actual in checks
        )

    def plan_changes(
        self, report: DiagnosticReport, setting_values: tuple[tuple[str, object], ...]
    ) -> ChangeSet:
        raise AdapterError("not_implemented", "planning belongs to Phase 3")


def parse_opencode_version(content: str) -> str | None:
    match = _VERSION.search(content.strip())
    return match.group(1) if match else None


def parse_jsonc(content: str) -> object:
    """Remove JSONC comments/trailing commas while preserving quoted strings."""
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(content):
        char = content[index]
        following = content[index + 1] if index + 1 < len(content) else ""
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
        elif char == "/" and following == "/":
            index += 2
            while index < len(content) and content[index] not in "\r\n":
                index += 1
        elif char == "/" and following == "*":
            end = content.find("*/", index + 2)
            if end < 0:
                raise ValueError("unterminated block comment")
            index = end + 2
        else:
            output.append(char)
            index += 1
    without_comments = "".join(output)
    without_trailing_commas = re.sub(r",(?=\s*[}\]])", "", without_comments)
    return json.loads(without_trailing_commas)


def extract_connection(document: dict[str, object]) -> tuple[str | None, str | None, str | None]:
    provider = _string(document.get("provider"))
    model = _string(document.get("model"))
    base_url = _string(document.get("baseURL") or document.get("base_url"))
    providers = document.get("providers") or document.get("provider")
    if isinstance(providers, dict):
        if provider and isinstance(providers.get(provider), dict):
            selected = providers[provider]
        elif len(providers) == 1:
            provider, selected = next(iter(providers.items()))
        else:
            selected = None
        if isinstance(selected, dict):
            options = selected.get("options") if isinstance(selected.get("options"), dict) else selected
            base_url = _string(options.get("baseURL") or options.get("base_url")) or base_url
    return provider, model, base_url


def extract_settings(document: dict[str, object], keys: frozenset[str]) -> tuple[tuple[str, object], ...]:
    found: list[tuple[str, object]] = []

    def visit(value: object, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else key
                if key in keys:
                    collect_scalars(child, child_path, found)
                visit(child, child_path)
        elif isinstance(value, list):
            for position, child in enumerate(value):
                visit(child, f"{path}[{position}]")

    visit(document, "")
    return tuple(dict(found).items())


def extract_available_connections(
    document: dict[str, object],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    configured = document.get("providers") or document.get("provider")
    if not isinstance(configured, dict):
        return (), (), ()
    providers: list[str] = []
    models: list[str] = []
    base_urls: list[str] = []
    for provider_name, raw_provider in configured.items():
        if not isinstance(raw_provider, dict):
            continue
        providers.append(provider_name)
        options = raw_provider.get("options")
        if isinstance(options, dict):
            base_url = _string(options.get("baseURL") or options.get("base_url"))
            if base_url:
                base_urls.append(base_url)
        raw_models = raw_provider.get("models")
        if isinstance(raw_models, dict):
            models.extend(f"{provider_name}/{name}" for name in raw_models)
    return tuple(providers), tuple(models), tuple(dict.fromkeys(base_urls))


def collect_scalars(value: object, path: str, destination: list[tuple[str, object]] | None = None) -> None:
    target = destination if destination is not None else []
    if isinstance(value, dict):
        for key, child in value.items():
            collect_scalars(child, f"{path}.{key}", target)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            collect_scalars(child, f"{path}[{index}]", target)
    elif isinstance(value, (str, int, float, bool, type(None))):
        target.append((path, value))


def _ollama_compatible(
    provider: str | None,
    base_url: str | None,
    providers: tuple[str, ...] = (),
    base_urls: tuple[str, ...] = (),
) -> bool | None:
    if provider and "ollama" in provider.lower():
        return True
    if base_url:
        return "11434" in base_url or "ollama" in base_url.lower()
    if providers or base_urls:
        return any("ollama" in item.lower() for item in providers + base_urls)
    return None


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None
