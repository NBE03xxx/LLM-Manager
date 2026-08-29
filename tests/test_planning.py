import unittest

from llm_manager.application.errors import AdapterError
from llm_manager.domain.enums import Confidence, ReportStatus, Severity
from llm_manager.domain.models import (
    DiagnosticReport,
    LocalizedMessage,
    OpenCodeInfo,
    Recommendation,
    Risk,
)
from llm_manager.planning import ConfigSnapshot, OpenCodeChangePlanner, locate_scalar_spans

from tests.fixtures import host_info


PATH = "/home/test/.config/opencode/opencode.jsonc"
CONTENT = '''{
  // Keep this comment
  "provider": {"ollama": {"options": {"apiKey": "do-not-leak"}}},
  "compaction": {
    "auto": false,
    "prune": false,
  },
}
'''


def report(version: str = "1.18.25") -> DiagnosticReport:
    return DiagnosticReport(
        "report-plan",
        "1.0",
        host_info(),
        ReportStatus.COMPLETE,
        opencode=OpenCodeInfo(installed=True, version=version, active_config=PATH),
    )


def recommendation(key: str = "compaction.auto", current=False, desired=True, actionable=True) -> Recommendation:
    return Recommendation(
        "rec-1",
        "rule-1",
        1,
        PATH,
        key,
        current,
        desired,
        LocalizedMessage("reason"),
        Severity.MEDIUM,
        Confidence.HIGH,
        LocalizedMessage("impact"),
        Risk(Severity.LOW, LocalizedMessage("risk")),
        False,
        False,
        actionable=actionable,
    )


class JsoncSpanTests(unittest.TestCase):
    def test_locates_existing_scalar_without_losing_comments(self) -> None:
        spans = locate_scalar_spans(CONTENT)
        span = spans["compaction.auto"]
        updated = CONTENT[: span.start] + "true" + CONTENT[span.end :]
        self.assertIn("// Keep this comment", updated)
        self.assertIn('"apiKey": "do-not-leak"', updated)
        self.assertIn('"auto": true', updated)

    def test_rejects_malformed_jsonc(self) -> None:
        with self.assertRaises(AdapterError):
            locate_scalar_spans('{"x": /* unterminated')


class OpenCodePlannerTests(unittest.TestCase):
    def test_plans_source_span_scalar_replacement(self) -> None:
        snapshot = ConfigSnapshot.capture(PATH, CONTENT)
        change_set = OpenCodeChangePlanner().plan(report(), (recommendation(),), snapshot)
        self.assertEqual(len(change_set.changes), 1)
        change = change_set.changes[0]
        self.assertEqual(change.replacement_text, "true")
        self.assertEqual(change.before_hash, snapshot.sha256)
        self.assertNotIn("do-not-leak", change.diff)

    def test_plan_is_deterministic(self) -> None:
        snapshot = ConfigSnapshot.capture(PATH, CONTENT)
        planner = OpenCodeChangePlanner()
        self.assertEqual(
            planner.plan(report(), (recommendation(),), snapshot),
            planner.plan(report(), (recommendation(),), snapshot),
        )

    def test_unsupported_version_is_rejected(self) -> None:
        with self.assertRaises(AdapterError):
            OpenCodeChangePlanner().plan(report("1.18.18"), (recommendation(),), ConfigSnapshot.capture(PATH, CONTENT))

    def test_allowlist_is_enforced(self) -> None:
        with self.assertRaises(AdapterError):
            OpenCodeChangePlanner().plan(
                report(), (recommendation("provider.ollama.options.apiKey", "do-not-leak", "new"),), ConfigSnapshot.capture(PATH, CONTENT)
            )

    def test_non_actionable_recommendation_is_ignored(self) -> None:
        change_set = OpenCodeChangePlanner().plan(
            report(), (recommendation(actionable=False),), ConfigSnapshot.capture(PATH, CONTENT)
        )
        self.assertFalse(change_set.changes)

    def test_wrong_replacement_type_is_rejected(self) -> None:
        with self.assertRaises(AdapterError):
            OpenCodeChangePlanner().plan(
                report(), (recommendation(desired="true"),), ConfigSnapshot.capture(PATH, CONTENT)
            )


if __name__ == "__main__":
    unittest.main()
