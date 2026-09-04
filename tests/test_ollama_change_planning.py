import unittest
from dataclasses import replace

from llm_manager.adapters.fakes import FakeHostAdapter
from llm_manager.application.change_planning import BuildSelectedOllamaChangePlan
from llm_manager.application.errors import AdapterError
from llm_manager.application.optimization import stable_hash
from llm_manager.application.ports import CancellationToken, FileStat
from llm_manager.domain.models import OptimizationPlan, utc_now
from llm_manager.planning.ollama import DROP_IN_PATH
from tests.test_ollama_planning import recommendation, report


class _HelperProbe:
    def __init__(self, ready=True):
        self.ready = ready
        self.calls = 0

    def root_apply_allowed(self, host, cancellation):
        self.calls += 1
        return self.ready


class _Host(FakeHostAdapter):
    def __init__(self, host_info, files=None, *, unsafe=False):
        super().__init__(host_info, files or {})
        self.unsafe = unsafe

    def stat(self, path, cancellation):
        self.calls.append(("stat", path))
        content = self.files.get(path)
        return FileStat(path, content is not None, is_symlink=self.unsafe)


def selected_plan():
    current = report()
    item = recommendation("OLLAMA_FLASH_ATTENTION", True)
    plan = OptimizationPlan(
        "plan-ollama",
        current.report_id,
        stable_hash(current),
        "balanced",
        "1.0.0",
        (item,),
        selected_ids=(item.recommendation_id,),
        created_at=utc_now(),
    )
    return current, plan


class BuildSelectedOllamaChangePlanTests(unittest.TestCase):
    def test_rechecks_identity_helper_and_existing_fixed_drop_in(self):
        current, plan = selected_plan()
        content = b'[Service]\nEnvironment="OLLAMA_FLASH_ATTENTION=0"\n'
        host = _Host(current.host, {DROP_IN_PATH: content})
        probe = _HelperProbe()

        result = BuildSelectedOllamaChangePlan(probe).execute(
            plan, current, host, CancellationToken()
        )

        change = result.change_set.changes[0]
        self.assertEqual(change.target, DROP_IN_PATH)
        self.assertTrue(change.requires_root)
        self.assertIsNotNone(change.before_hash)
        self.assertEqual(probe.calls, 1)
        self.assertEqual([call[0] for call in host.calls], ["identify", "stat", "read_file"])

    def test_missing_drop_in_is_planned_without_content_read(self):
        current, plan = selected_plan()
        host = _Host(current.host)
        result = BuildSelectedOllamaChangePlan(_HelperProbe()).execute(
            plan, current, host, CancellationToken()
        )
        self.assertIsNone(result.change_set.changes[0].before_hash)
        self.assertEqual([call[0] for call in host.calls], ["identify", "stat"])

    def test_rejects_stale_identity_unready_helper_and_unsafe_target(self):
        current, plan = selected_plan()
        changed = replace(current.host, host_id="local:changed")
        with self.assertRaisesRegex(AdapterError, "identity changed"):
            BuildSelectedOllamaChangePlan(_HelperProbe()).execute(
                plan, current, _Host(changed), CancellationToken()
            )
        host = _Host(current.host)
        with self.assertRaises(AdapterError) as caught:
            BuildSelectedOllamaChangePlan(_HelperProbe(False)).execute(
                plan, current, host, CancellationToken()
            )
        self.assertEqual(caught.exception.code, "privileged_helper_unavailable")
        with self.assertRaises(AdapterError) as caught:
            BuildSelectedOllamaChangePlan(_HelperProbe()).execute(
                plan, current, _Host(current.host, {DROP_IN_PATH: b"x"}, unsafe=True), CancellationToken()
            )
        self.assertEqual(caught.exception.code, "unsafe_target")

    def test_rejects_non_root_or_mixed_selection_before_host_io(self):
        current, plan = selected_plan()
        invalid = replace(plan.recommendations[0], target="opencode", requires_root=False)
        plan = replace(plan, recommendations=(invalid,))
        host = _Host(current.host)
        with self.assertRaises(AdapterError) as caught:
            BuildSelectedOllamaChangePlan(_HelperProbe()).execute(
                plan, current, host, CancellationToken()
            )
        self.assertEqual(caught.exception.code, "selection_invalid")
        self.assertEqual(host.calls, [])


if __name__ == "__main__":
    unittest.main()
