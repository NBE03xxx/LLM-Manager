from __future__ import annotations

from dataclasses import dataclass

from llm_manager.domain.enums import Severity, ValidationStatus
from llm_manager.domain.models import ChangeSet, LocalizedMessage, ValidationResult

from .errors import AdapterError
from .ports import CancellationToken, ClientAdapter, HostPort, OllamaPort, RuntimeValidatorPort


@dataclass(slots=True)
class ProductRuntimeValidator(RuntimeValidatorPort):
    host: HostPort
    ollama: OllamaPort
    client: ClientAdapter

    def validate(self, change_set: ChangeSet, cancellation: CancellationToken) -> tuple[ValidationResult, ...]:
        checks = {check for change in change_set.changes for check in change.validation_checks}
        results: list[ValidationResult] = []
        if any(check.startswith(("ollama.", "systemd.")) for check in checks):
            try:
                info = self.ollama.inspect(self.host, cancellation)
                if "ollama.service.active" in checks:
                    actual = info.service.active_state if info.service else None
                    results.append(_result("ollama.service.active", actual == "active", "active", actual))
                if "ollama.environment.effective" in checks:
                    expected = _expected_ollama_environment(change_set)
                    observed = dict(info.environment)
                    for key, value in expected:
                        results.append(_result(f"ollama.environment.{key}", observed.get(key) == value, value, observed.get(key)))
            except AdapterError as error:
                results.append(_result("ollama.inspect", False, "available", error.code))
            if "ollama.api.connectivity" in checks:
                try:
                    results.extend(self.ollama.validate_api(self.host, cancellation))
                except AdapterError as error:
                    results.append(_result("ollama.api.connectivity", False, "reachable", error.code))
        if any(check.startswith("opencode.") for check in checks):
            try:
                results.extend(self.client.validate(self.host, cancellation))
            except AdapterError as error:
                results.append(_result("opencode.config", False, "valid", error.code))
        return tuple(results)


def _expected_ollama_environment(change_set: ChangeSet) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    for change in change_set.changes:
        if not isinstance(change.after, tuple):
            continue
        for item in change.after:
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str):
                result.append((item[0], str(item[1])))
    return tuple(result)


def _result(check: str, passed: bool, expected: str | None, actual: str | None) -> ValidationResult:
    return ValidationResult(
        validation_id=check,
        scope="runtime",
        check=check,
        status=ValidationStatus.PASSED if passed else ValidationStatus.FAILED,
        expected=expected,
        actual=actual,
        severity=Severity.INFO if passed else Severity.HIGH,
        message=LocalizedMessage(f"validation.{check}.{'passed' if passed else 'failed'}"),
    )
