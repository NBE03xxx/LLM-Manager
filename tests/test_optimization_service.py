import unittest

from llm_manager.application.optimization import GenerateOptimizationPlan, stable_hash
from llm_manager.optimization import AGENT, CATALOG_VERSION, RuleEngine, default_catalog

from tests.test_optimization import diagnostic


class GenerateOptimizationPlanTests(unittest.TestCase):
    def test_plan_is_bound_to_report_profile_and_catalog(self) -> None:
        report = diagnostic()
        service = GenerateOptimizationPlan(RuleEngine(CATALOG_VERSION, default_catalog()))
        plan = service.execute("plan-1", report, AGENT)
        self.assertEqual(plan.report_hash, stable_hash(report))
        self.assertEqual(plan.profile, AGENT)
        self.assertEqual(plan.rule_catalog_version, CATALOG_VERSION)
        self.assertTrue(plan.recommendations)

    def test_generation_does_not_select_or_plan_changes(self) -> None:
        plan = GenerateOptimizationPlan(RuleEngine(CATALOG_VERSION, default_catalog())).execute(
            "plan-1", diagnostic(), AGENT
        )
        self.assertEqual(plan.selected_ids, ())
        self.assertIsNone(plan.change_set)

    def test_report_hash_is_deterministic(self) -> None:
        report = diagnostic()
        self.assertEqual(stable_hash(report), stable_hash(report))


if __name__ == "__main__":
    unittest.main()
