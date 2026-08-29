import unittest
from dataclasses import dataclass, replace

from llm_manager.domain.enums import Confidence, ProbeStatus, ReportStatus, Severity
from llm_manager.domain.models import (
    DiagnosticReport,
    LocalizedMessage,
    OllamaInfo,
    OpenCodeInfo,
    Recommendation,
    Risk,
)
from llm_manager.optimization import AGENT, BALANCED, CODING, CATALOG_VERSION, RuleEngine, default_catalog

from tests.fixtures import host_info


def diagnostic(version: str = "1.18.25", ollama_ok: bool = True) -> DiagnosticReport:
    return DiagnosticReport(
        report_id="report-opt",
        schema_version="1.0",
        host=host_info(),
        status=ReportStatus.COMPLETE,
        ollama=OllamaInfo(
            installed=ollama_ok,
            version="0.33.2" if ollama_ok else None,
            api_connectivity=ProbeStatus.OK if ollama_ok else ProbeStatus.UNAVAILABLE,
        ),
        opencode=OpenCodeInfo(
            installed=True,
            version=version,
            active_config="/home/test/.config/opencode/opencode.jsonc",
            context_settings=(("compaction.auto", False), ("compaction.prune", False)),
            ollama_compatible=True,
        ),
    )


class RuleEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = RuleEngine(CATALOG_VERSION, default_catalog())

    def test_profiles_are_distinct(self) -> None:
        self.assertEqual({profile.profile_id for profile in (BALANCED, CODING, AGENT)}, {"balanced", "coding", "agent"})
        self.assertNotEqual(CODING.constraints, AGENT.constraints)

    def test_agent_compaction_is_actionable_only_on_baseline(self) -> None:
        recommendations = self.engine.evaluate(diagnostic(), AGENT)
        compaction = [item for item in recommendations if item.setting_key.startswith("compaction.")]
        self.assertEqual(len(compaction), 2)
        self.assertTrue(all(item.actionable for item in compaction))

    def test_balanced_does_not_receive_agent_compaction(self) -> None:
        self.assertFalse(self.engine.evaluate(diagnostic(), BALANCED))

    def test_unknown_nearby_version_is_readonly(self) -> None:
        recommendations = self.engine.evaluate(diagnostic("1.18.18"), AGENT)
        self.assertTrue(any(item.setting_key == "version_compatibility" for item in recommendations))
        self.assertFalse(any(item.actionable for item in recommendations))

    def test_invalid_compaction_type_is_not_actionable(self) -> None:
        item = diagnostic()
        info = replace(item.opencode, context_settings=(("compaction.auto", "yes"),))
        item = replace(item, opencode=info)
        recommendations = self.engine.evaluate(item, AGENT)
        self.assertTrue(recommendations)
        self.assertFalse(any(value.actionable for value in recommendations))

    def test_unavailable_ollama_yields_manual_review(self) -> None:
        recommendations = self.engine.evaluate(diagnostic(ollama_ok=False), CODING)
        item = next(value for value in recommendations if value.setting_key == "connectivity")
        self.assertEqual(item.severity, Severity.HIGH)
        self.assertFalse(item.actionable)

    def test_evaluation_is_deterministic(self) -> None:
        self.assertEqual(self.engine.evaluate(diagnostic(), AGENT), self.engine.evaluate(diagnostic(), AGENT))


@dataclass(frozen=True)
class StaticRule:
    rule_id: str
    recommended: bool
    priority: int
    version: int = 1
    profiles: frozenset[str] = frozenset({"agent"})

    def evaluate(self, report, profile):
        return Recommendation(
            recommendation_id=self.rule_id,
            rule_id=self.rule_id,
            rule_version=1,
            target="/config",
            setting_key="compaction.auto",
            current_value=False,
            recommended_value=self.recommended,
            reason=LocalizedMessage("reason"),
            severity=Severity.LOW,
            confidence=Confidence.HIGH,
            impact=LocalizedMessage("impact"),
            risk=Risk(Severity.LOW, LocalizedMessage("risk")),
            requires_restart=False,
            requires_root=False,
            actionable=True,
        )


class ConflictTests(unittest.TestCase):
    def test_conflicting_values_are_not_actionable(self) -> None:
        engine = RuleEngine("test", (StaticRule("a", True, 1), StaticRule("b", False, 1)))
        values = engine.evaluate(diagnostic(), AGENT)
        self.assertEqual(len(values), 2)
        self.assertTrue(all(not item.actionable and item.conflicts_with for item in values))


if __name__ == "__main__":
    unittest.main()
