import unittest
from dataclasses import replace

from llm_manager.domain.enums import Confidence, Severity
from llm_manager.domain.models import LocalizedMessage, Recommendation, Risk
from llm_manager.optimization import AGENT
from llm_manager.ui.i18n import Catalog
from llm_manager.ui.recommendations import (
    generate_recommendation_plan,
    present_recommendations,
    profile_by_id,
)
from tests.test_optimization import diagnostic


class RecommendationPresentationTests(unittest.TestCase):
    def test_generates_and_presents_agent_recommendations(self) -> None:
        plan = generate_recommendation_plan(diagnostic(), AGENT)
        view = present_recommendations(plan, Catalog("en"))
        self.assertEqual(view.profile_id, "agent")
        self.assertEqual(len(view.items), 2)
        self.assertTrue(all(item.actionable for item in view.items))
        self.assertIn("2 recommendations", view.summary)
        self.assertIn("compaction.", view.items[0].title)

    def test_japanese_profile_and_summary_are_localized(self) -> None:
        view = present_recommendations(
            generate_recommendation_plan(diagnostic(), AGENT), Catalog("ja")
        )
        self.assertEqual(view.profile_name, "エージェント")
        self.assertIn("推奨 2件", view.summary)

    def test_sensitive_setting_values_are_redacted(self) -> None:
        item = Recommendation(
            "secret", "secret", 1, "/config", "provider.apiKey", "old", "new",
            LocalizedMessage("reason"), Severity.HIGH, Confidence.HIGH,
            LocalizedMessage("impact"), Risk(Severity.HIGH, LocalizedMessage("risk")),
            False, False,
        )
        plan = generate_recommendation_plan(diagnostic(), AGENT)
        view = present_recommendations(
            replace(plan, recommendations=(item,)),
            Catalog("en"),
        )
        self.assertIn("<redacted> → <redacted>", view.items[0].title)
        self.assertNotIn("old", view.items[0].title)

    def test_rejects_unknown_profile(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown_optimization_profile"):
            profile_by_id("fastest")


if __name__ == "__main__":
    unittest.main()
