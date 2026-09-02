import unittest
from dataclasses import replace
from datetime import timedelta

from llm_manager.adapters.fakes import FakeHostAdapter
from llm_manager.application.change_planning import BuildSelectedOpenCodeChangePlan
from llm_manager.application.errors import AdapterError
from llm_manager.application.optimization import GenerateOptimizationPlan
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import utc_now
from llm_manager.optimization import AGENT, CATALOG_VERSION, RuleEngine, default_catalog
from llm_manager.ui.recommendations import select_recommendations
from tests.test_optimization import diagnostic


CONTENT = '{"compaction":{"auto":false,"prune":false}}\n'


def selected_plan():
    report = diagnostic()
    plan = GenerateOptimizationPlan(RuleEngine(CATALOG_VERSION, default_catalog())).execute(
        "plan-change", report, AGENT
    )
    return report, select_recommendations(
        plan, tuple(item.recommendation_id for item in plan.recommendations)
    )


class BuildSelectedOpenCodeChangePlanTests(unittest.TestCase):
    def test_rereads_source_and_binds_before_hash_and_selected_ids(self) -> None:
        report, plan = selected_plan()
        path = report.opencode.active_config
        host = FakeHostAdapter(report.host, {path: CONTENT.encode()})
        result = BuildSelectedOpenCodeChangePlan().execute(
            plan, report, host, CancellationToken()
        )
        self.assertEqual(len(result.change_set.changes), 2)
        self.assertEqual(result.selected_ids, plan.selected_ids)
        self.assertTrue(all(change.before_hash for change in result.change_set.changes))
        self.assertEqual(host.calls[0][0], "identify")
        self.assertEqual(host.calls[1], ("read_file", path))

    def test_rejects_stale_report_before_host_access(self) -> None:
        report, plan = selected_plan()
        host = FakeHostAdapter(report.host)
        with self.assertRaisesRegex(AdapterError, "not bound"):
            BuildSelectedOpenCodeChangePlan().execute(
                replace(plan, report_hash="0" * 64), report, host, CancellationToken()
            )
        self.assertEqual(host.calls, [])

    def test_rejects_expired_plan_and_changed_host_identity(self) -> None:
        report, plan = selected_plan()
        host = FakeHostAdapter(report.host)
        with self.assertRaisesRegex(AdapterError, "expired"):
            BuildSelectedOpenCodeChangePlan().execute(
                replace(plan, expires_at=utc_now() - timedelta(seconds=1)),
                report,
                host,
                CancellationToken(),
            )
        changed = replace(report.host, fingerprint="SHA256:" + "A" * 43)
        with self.assertRaisesRegex(AdapterError, "identity changed"):
            BuildSelectedOpenCodeChangePlan().execute(
                plan, report, FakeHostAdapter(changed), CancellationToken()
            )

    def test_rejects_unselected_nonactionable_and_non_utf8(self) -> None:
        report, plan = selected_plan()
        path = report.opencode.active_config
        service = BuildSelectedOpenCodeChangePlan()
        with self.assertRaisesRegex(AdapterError, "select at least"):
            service.execute(replace(plan, selected_ids=()), report, FakeHostAdapter(report.host), CancellationToken())
        bad = replace(plan.recommendations[0], actionable=False)
        with self.assertRaisesRegex(AdapterError, "not actionable"):
            service.execute(
                replace(plan, recommendations=(bad, *plan.recommendations[1:])),
                report,
                FakeHostAdapter(report.host),
                CancellationToken(),
            )
        with self.assertRaisesRegex(AdapterError, "not UTF-8"):
            service.execute(
                plan, report, FakeHostAdapter(report.host, {path: b"\xff"}), CancellationToken()
            )


if __name__ == "__main__":
    unittest.main()
