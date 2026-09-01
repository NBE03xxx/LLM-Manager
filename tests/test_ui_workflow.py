import unittest
from dataclasses import replace

from llm_manager.domain.enums import ReportStatus
from llm_manager.ui.workflow import GuiPresenter, GuiStep, WorkflowStatus

from tests.fixtures import report


class GuiPresenterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.presenter = GuiPresenter()

    def test_diagnosis_requires_host_and_prevents_double_start(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "host_required"):
            self.presenter.begin_diagnosis()
        self.presenter.select_host("host-1")
        self.presenter.begin_diagnosis()
        with self.assertRaisesRegex(RuntimeError, "workflow_busy"):
            self.presenter.begin_diagnosis()

    def test_complete_diagnosis_advances_to_recommendations(self) -> None:
        self.presenter.select_host("host-1")
        self.presenter.begin_diagnosis()
        state = self.presenter.finish_diagnosis(report())
        self.assertEqual(state.step, GuiStep.RECOMMENDATIONS)
        self.assertEqual(state.status, WorkflowStatus.SUCCESS)

    def test_partial_report_remains_actionable_and_visible(self) -> None:
        self.presenter.select_host("host-1")
        self.presenter.begin_diagnosis()
        state = self.presenter.finish_diagnosis(replace(report(), status=ReportStatus.PARTIAL))
        self.assertEqual(state.step, GuiStep.RECOMMENDATIONS)
        self.assertEqual(state.status, WorkflowStatus.PARTIAL)

    def test_failed_report_stays_on_diagnose(self) -> None:
        self.presenter.select_host("host-1")
        self.presenter.begin_diagnosis()
        state = self.presenter.finish_diagnosis(replace(report(), status=ReportStatus.FAILED))
        self.assertEqual(state.step, GuiStep.DIAGNOSE)
        self.assertEqual(state.status, WorkflowStatus.FAILED)

    def test_host_mismatch_is_rejected(self) -> None:
        self.presenter.select_host("another-host")
        self.presenter.begin_diagnosis()
        with self.assertRaisesRegex(ValueError, "report_host_mismatch"):
            self.presenter.finish_diagnosis(report())

    def test_cancel_request_is_idempotent(self) -> None:
        self.presenter.select_host("host-1")
        self.presenter.begin_diagnosis()
        first = self.presenter.request_cancel()
        second = self.presenter.request_cancel()
        self.assertEqual(first, second)
        self.assertEqual(second.status, WorkflowStatus.CANCEL_REQUESTED)

    def test_changed_plan_and_host_invalidate_approval(self) -> None:
        self.presenter.select_host("host-1")
        self.presenter.begin_diagnosis()
        self.presenter.finish_diagnosis(report())
        self.presenter.review_plan("plan-a")
        self.assertTrue(self.presenter.approve_plan().approved)
        self.assertFalse(self.presenter.review_plan("plan-b").approved)
        self.presenter.approve_plan()
        self.assertFalse(self.presenter.select_host("host-2").approved)


if __name__ == "__main__":
    unittest.main()
