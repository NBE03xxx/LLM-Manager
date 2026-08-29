import unittest

from llm_manager.adapters.fakes import FakeClientAdapter, FakeHostAdapter, FakeOllamaAdapter
from llm_manager.application.errors import OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.application.services import DiagnoseHost
from llm_manager.domain.enums import ReportStatus
from llm_manager.domain.models import OllamaInfo, OpenCodeInfo

from tests.fixtures import host_info


class DiagnoseHostTests(unittest.TestCase):
    def make_service(self) -> DiagnoseHost:
        return DiagnoseHost(
            FakeHostAdapter(host_info()),
            FakeOllamaAdapter(OllamaInfo(installed=True, version="0.33.2")),
            FakeClientAdapter(OpenCodeInfo(installed=True, version="1.18.25")),
        )

    def test_complete_report(self) -> None:
        result = self.make_service().execute("report", CancellationToken())
        self.assertEqual(result.status, ReportStatus.COMPLETE)
        self.assertEqual(result.ollama.version, "0.33.2")  # type: ignore[union-attr]

    def test_one_adapter_failure_yields_partial_report(self) -> None:
        service = self.make_service()
        service.client.failure_code = "parse_failed"  # type: ignore[attr-defined]
        result = service.execute("report", CancellationToken())
        self.assertEqual(result.status, ReportStatus.PARTIAL)
        self.assertIsNone(result.opencode)

    def test_both_adapter_failures_yield_failed_report(self) -> None:
        service = self.make_service()
        service.ollama.failure_code = "timeout"  # type: ignore[attr-defined]
        service.client.failure_code = "parse_failed"  # type: ignore[attr-defined]
        result = service.execute("report", CancellationToken())
        self.assertEqual(result.status, ReportStatus.FAILED)

    def test_pre_cancelled_request_does_not_touch_host(self) -> None:
        service = self.make_service()
        with self.assertRaises(OperationCancelled):
            service.execute("report", CancellationToken(cancelled=True))
        self.assertEqual(service.host.calls, [])  # type: ignore[attr-defined]

    def test_helper_readiness_controls_root_apply_capability(self) -> None:
        for ready in (True, False):
            with self.subTest(ready=ready):
                service = self.make_service()
                service.helper_probe = _HelperProbe(ready)
                result = service.execute("report", CancellationToken())
                self.assertEqual(result.host.capabilities.can_elevate, ready)
                self.assertEqual(
                    "privileged_helper_unavailable" in result.host.capabilities.limitations,
                    not ready,
                )

    def test_helper_probe_failure_fails_closed_without_failing_diagnosis(self) -> None:
        service = self.make_service()
        service.helper_probe = _HelperProbe(True, fail=True)
        result = service.execute("report", CancellationToken())
        self.assertEqual(result.status, ReportStatus.COMPLETE)
        self.assertFalse(result.host.capabilities.can_elevate)


class _HelperProbe:
    def __init__(self, ready, fail=False):
        self.ready = ready
        self.fail = fail

    def root_apply_allowed(self, host, cancellation):
        if self.fail:
            raise OSError("injected helper probe failure")
        return self.ready


if __name__ == "__main__":
    unittest.main()
