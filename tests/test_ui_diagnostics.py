import unittest
from dataclasses import replace

from llm_manager.domain.enums import ProbeStatus, ReportStatus, Severity
from llm_manager.domain.models import (
    DiagnosticFinding,
    HardwareInfo,
    LocalizedMessage,
    ProbeResult,
    SystemInfo,
)
from llm_manager.ui.diagnostics import present_diagnostic_report
from llm_manager.ui.i18n import Catalog

from tests.fixtures import report


class DiagnosticPresentationTests(unittest.TestCase):
    def test_presents_core_results_when_recommendations_can_be_empty(self) -> None:
        source = report()
        value = replace(
            source,
            host=replace(source.host, hostname="workstation"),
            system=SystemInfo("Ubuntu", "26.04", "6.17.0", "x86_64"),
            hardware=HardwareInfo(
                cpu="Example CPU",
                logical_cores=16,
                ram_total_bytes=32 * 1024**3,
                ram_available_bytes=20 * 1024**3,
                swap_total_bytes=8 * 1024**3,
                swap_free_bytes=8 * 1024**3,
            ),
            probe_results=(
                ("system", ProbeResult(ProbeStatus.OK, object())),
                (
                    "gpu",
                    ProbeResult(
                        ProbeStatus.UNAVAILABLE,
                        error_code="command_unavailable",
                        error_message="must not be displayed",
                    ),
                ),
            ),
            findings=(
                DiagnosticFinding(
                    "finding-1",
                    "runtime",
                    Severity.LOW,
                    LocalizedMessage("test.finding", fallback_text="fallback"),
                ),
            ),
        )

        view = present_diagnostic_report(value, Catalog("ja"))

        self.assertIn("Test host", view.summary)
        self.assertIn("probe成功 1/2", view.summary)
        self.assertIn("問題 2件", view.summary)
        rendered = "\n".join(view.items)
        self.assertIn("Ubuntu 26.04", rendered)
        self.assertIn("Example CPU", rendered)
        self.assertIn("Ollama", rendered)
        self.assertIn("OpenCode", rendered)
        self.assertIn("command_unavailable", rendered)
        self.assertNotIn("must not be displayed", rendered)

    def test_partial_report_explicitly_marks_missing_sections(self) -> None:
        value = replace(
            report(),
            status=ReportStatus.PARTIAL,
            system=None,
            hardware=None,
            ollama=None,
            opencode=None,
        )

        view = present_diagnostic_report(value, Catalog("en"))

        self.assertIn("partial", view.summary)
        self.assertIn("System: unavailable", view.items)
        self.assertIn("Hardware: unavailable", view.items)
        self.assertIn("Ollama: diagnostic unavailable", view.items)
        self.assertIn("OpenCode: diagnostic unavailable", view.items)


if __name__ == "__main__":
    unittest.main()
