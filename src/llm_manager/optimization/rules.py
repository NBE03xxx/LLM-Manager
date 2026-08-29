from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from llm_manager.domain.enums import Confidence, ProbeStatus, Severity
from llm_manager.domain.models import (
    DiagnosticReport,
    LocalizedMessage,
    OptimizationProfile,
    Recommendation,
    Risk,
)


class Rule(Protocol):
    rule_id: str
    version: int
    priority: int
    profiles: frozenset[str]

    def evaluate(
        self, report: DiagnosticReport, profile: OptimizationProfile
    ) -> Recommendation | None: ...


@dataclass(frozen=True, slots=True)
class OllamaUnavailableRule:
    rule_id: str = "connectivity.ollama-unavailable"
    version: int = 1
    priority: int = 100
    profiles: frozenset[str] = frozenset({"balanced", "coding", "agent"})

    def evaluate(self, report: DiagnosticReport, profile: OptimizationProfile) -> Recommendation | None:
        if profile.profile_id not in self.profiles or report.opencode is None:
            return None
        if report.opencode.ollama_compatible is not True:
            return None
        if report.ollama is not None and report.ollama.api_connectivity is ProbeStatus.OK:
            return None
        return Recommendation(
            recommendation_id=f"{self.rule_id}:{profile.profile_id}",
            rule_id=self.rule_id,
            rule_version=self.version,
            target="ollama.api",
            setting_key="connectivity",
            current_value="unavailable",
            recommended_value="manual_review",
            reason=_message("recommendation.ollama_unavailable.reason"),
            severity=Severity.HIGH,
            confidence=Confidence.HIGH,
            impact=_message("recommendation.ollama_unavailable.impact"),
            risk=Risk(Severity.LOW, _message("recommendation.manual_review.risk")),
            requires_restart=False,
            requires_root=False,
            evidence=(("opencode_ollama_compatible", True), ("ollama_api", "unavailable")),
            actionable=False,
        )


@dataclass(frozen=True, slots=True)
class UnsupportedOpenCodeVersionRule:
    supported_version: str = "1.18.25"
    rule_id: str = "compatibility.opencode-version"
    version: int = 1
    priority: int = 1000
    profiles: frozenset[str] = frozenset({"balanced", "coding", "agent"})

    def evaluate(self, report: DiagnosticReport, profile: OptimizationProfile) -> Recommendation | None:
        info = report.opencode
        if profile.profile_id not in self.profiles or info is None or not info.installed:
            return None
        if info.version == self.supported_version:
            return None
        return Recommendation(
            recommendation_id=f"{self.rule_id}:{profile.profile_id}",
            rule_id=self.rule_id,
            rule_version=self.version,
            target="opencode",
            setting_key="version_compatibility",
            current_value=info.version,
            recommended_value=self.supported_version,
            reason=_message(
                "recommendation.opencode_unsupported.reason",
                (("observed", info.version), ("baseline", self.supported_version)),
            ),
            severity=Severity.MEDIUM,
            confidence=Confidence.HIGH,
            impact=_message("recommendation.opencode_unsupported.impact"),
            risk=Risk(Severity.HIGH, _message("recommendation.unsupported_change.risk")),
            requires_restart=False,
            requires_root=False,
            evidence=(("opencode_version", info.version),),
            actionable=False,
        )


@dataclass(frozen=True, slots=True)
class AgentCompactionRule:
    setting_key: str
    desired: bool
    rule_id: str
    priority: int
    version: int = 1
    profiles: frozenset[str] = frozenset({"agent"})

    def evaluate(self, report: DiagnosticReport, profile: OptimizationProfile) -> Recommendation | None:
        info = report.opencode
        if profile.profile_id not in self.profiles or info is None or not info.installed:
            return None
        missing = object()
        current = dict(info.context_settings).get(self.setting_key, missing)
        if current is missing or (type(current) is bool and current is self.desired):
            return None
        supported = (
            info.version == "1.18.25"
            and info.active_config is not None
            and not info.parse_warnings
            and type(current) is bool
        )
        return Recommendation(
            recommendation_id=f"{self.rule_id}:{profile.profile_id}",
            rule_id=self.rule_id,
            rule_version=self.version,
            target=info.active_config or "opencode.config",
            setting_key=self.setting_key,
            current_value=current,
            recommended_value=self.desired,
            reason=_message("recommendation.agent_compaction.reason", (("setting", self.setting_key),)),
            severity=Severity.MEDIUM,
            confidence=Confidence.HIGH if supported else Confidence.LOW,
            impact=_message("recommendation.agent_compaction.impact"),
            risk=Risk(
                Severity.LOW,
                _message("recommendation.agent_compaction.risk"),
                (_message("recommendation.backup_and_validate"),),
            ),
            requires_restart=False,
            requires_root=False,
            evidence=(("opencode_version", info.version), ("current", current)),
            actionable=supported,
        )


def _message(
    key: str, arguments: tuple[tuple[str, str | int | float | bool | None], ...] = ()
) -> LocalizedMessage:
    return LocalizedMessage(key, arguments, key)
