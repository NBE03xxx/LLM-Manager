import unittest
from dataclasses import replace

from llm_manager.application.errors import AdapterError
from llm_manager.domain.enums import Confidence, ProbeStatus, ReportStatus, Severity
from llm_manager.domain.models import (
    DiagnosticReport,
    LocalizedMessage,
    OllamaInfo,
    Recommendation,
    Risk,
    ServiceInfo,
)
from llm_manager.planning import OllamaDropInPlanner, OllamaSettingPolicy

from tests.fixtures import host_info


def report(version: str = "0.33.2") -> DiagnosticReport:
    helper_ready_host = replace(
        host_info(),
        capabilities=replace(host_info().capabilities, can_elevate=True),
    )
    return DiagnosticReport(
        "report-ollama-plan",
        "1.0",
        helper_ready_host,
        ReportStatus.COMPLETE,
        ollama=OllamaInfo(
            installed=True,
            version=version,
            service=ServiceInfo("ollama.service", "loaded", "active", "running"),
            api_connectivity=ProbeStatus.OK,
        ),
    )


def recommendation(key: str, value: object) -> Recommendation:
    return Recommendation(
        f"rec:{key}",
        f"rule:{key}",
        1,
        "ollama.systemd",
        key,
        None,
        value,  # type: ignore[arg-type]
        LocalizedMessage("reason"),
        Severity.MEDIUM,
        Confidence.HIGH,
        LocalizedMessage("impact"),
        Risk(Severity.LOW, LocalizedMessage("risk")),
        True,
        True,
        actionable=True,
    )


class OllamaDropInPlannerTests(unittest.TestCase):
    def test_creates_only_dedicated_drop_in(self) -> None:
        change_set = OllamaDropInPlanner().plan(
            report(),
            (
                recommendation("OLLAMA_HOST", "127.0.0.1:11434"),
                recommendation("OLLAMA_FLASH_ATTENTION", True),
            ),
            None,
        )
        change = change_set.changes[0]
        self.assertEqual(change.target, "/etc/systemd/system/ollama.service.d/90-llm-manager.conf")
        self.assertTrue(change.requires_root)
        self.assertTrue(change.requires_restart)
        self.assertIn('Environment="OLLAMA_FLASH_ATTENTION=1"', change.replacement_text)

    def test_replaces_existing_drop_in_with_hash_precondition(self) -> None:
        content = '[Service]\nEnvironment="OLLAMA_FLASH_ATTENTION=0"\n'
        change = OllamaDropInPlanner().plan(
            report(), (recommendation("OLLAMA_FLASH_ATTENTION", True),), content
        ).changes[0]
        self.assertIsNotNone(change.before_hash)
        self.assertEqual(change.source_span, (0, len(content)))

    def test_numeric_setting_requires_verified_bounds(self) -> None:
        with self.assertRaises(AdapterError):
            OllamaDropInPlanner().plan(
                report(), (recommendation("OLLAMA_CONTEXT_LENGTH", 8192),), None
            )

    def test_selected_change_preserves_other_settings_and_comments(self) -> None:
        content = (
            '# Existing configuration\n[Service]\n'
            'Environment="OLLAMA_HOST=127.0.0.1:11434"\n\n'
            'Environment="OLLAMA_FLASH_ATTENTION=0"\n'
            '; Keep the established capacity\n'
            'Environment="OLLAMA_NUM_PARALLEL=2"\n'
        )
        change = OllamaDropInPlanner().plan(
            report(), (recommendation("OLLAMA_FLASH_ATTENTION", True),), content
        ).changes[0]
        self.assertEqual(
            change.replacement_text, content.replace('ATTENTION=0', 'ATTENTION=1')
        )
        self.assertEqual(change.after, (("OLLAMA_FLASH_ATTENTION", "1"),))

    def test_adds_selected_setting_without_removing_existing_last_line(self) -> None:
        content = '[Service]\nEnvironment="OLLAMA_HOST=127.0.0.1:11434"'
        change = OllamaDropInPlanner().plan(
            report(), (recommendation("OLLAMA_FLASH_ATTENTION", True),), content
        ).changes[0]
        self.assertEqual(
            change.replacement_text,
            content + '\nEnvironment="OLLAMA_FLASH_ATTENTION=1"\n',
        )

    def test_ambiguous_or_unsupported_existing_content_is_rejected(self) -> None:
        for content in (
            '[Service]\nExecStart=/usr/bin/ollama serve\n',
            '[Service]\nEnvironment="UNREVIEWED_KEY=value"\n',
            '[Service]\nEnvironment="OLLAMA_FLASH_ATTENTION=0"\n'
            'Environment="OLLAMA_FLASH_ATTENTION=1"\n',
            '[Service]\nEnvironment=\n',
            '[Service]\nEnvironment="OLLAMA_HOST=%H:11434"\n',
            '[Service]\nEnvironment="OLLAMA_KEEP_ALIVE=5m"\\\n',
            '[Service]\n# ambiguous continuation\\\n',
            '[Service]\r\nEnvironment="OLLAMA_FLASH_ATTENTION=0"\r\n',
            '[Service]\n# comment\x00\n',
            '[Service]\n[Service]\n',
            'Environment="OLLAMA_FLASH_ATTENTION=0"\n',
            '',
        ):
            with self.subTest(content=content):
                with self.assertRaises(AdapterError) as caught:
                    OllamaDropInPlanner().plan(
                        report(), (recommendation("OLLAMA_FLASH_ATTENTION", True),), content
                    )
                self.assertEqual(caught.exception.code, "unsupported_existing_drop_in")

    def test_duplicate_selected_key_is_rejected(self) -> None:
        with self.assertRaises(AdapterError) as caught:
            OllamaDropInPlanner().plan(
                report(),
                (recommendation("OLLAMA_FLASH_ATTENTION", True),
                 recommendation("OLLAMA_FLASH_ATTENTION", False)),
                None,
            )
        self.assertEqual(caught.exception.code, "duplicate_setting")

    def test_only_selected_last_line_is_replaced_without_adding_newline(self) -> None:
        content = '[Service]\nEnvironment="OLLAMA_FLASH_ATTENTION=0"'
        change = OllamaDropInPlanner().plan(
            report(), (recommendation("OLLAMA_FLASH_ATTENTION", True),), content
        ).changes[0]
        self.assertEqual(change.replacement_text, content.replace('ATTENTION=0', 'ATTENTION=1'))

    def test_numeric_setting_respects_injected_bounds(self) -> None:
        planner = OllamaDropInPlanner(
            OllamaSettingPolicy((("OLLAMA_CONTEXT_LENGTH", 2048, 32768),))
        )
        change = planner.plan(
            report(), (recommendation("OLLAMA_CONTEXT_LENGTH", 8192),), None
        ).changes[0]
        self.assertIn("OLLAMA_CONTEXT_LENGTH=8192", change.replacement_text)

    def test_external_bind_is_rejected(self) -> None:
        with self.assertRaises(AdapterError):
            OllamaDropInPlanner().plan(
                report(), (recommendation("OLLAMA_HOST", "0.0.0.0:11434"),), None
            )

    def test_unknown_version_is_rejected(self) -> None:
        with self.assertRaises(AdapterError):
            OllamaDropInPlanner().plan(
                report("0.34.0"), (recommendation("OLLAMA_FLASH_ATTENTION", True),), None
            )

    def test_missing_compatible_helper_blocks_root_change_plan(self) -> None:
        current = report()
        blocked = replace(
            current,
            host=replace(
                current.host,
                capabilities=replace(current.host.capabilities, can_elevate=False),
            ),
        )
        with self.assertRaises(AdapterError) as caught:
            OllamaDropInPlanner().plan(
                blocked, (recommendation("OLLAMA_FLASH_ATTENTION", True),), None
            )
        self.assertEqual(caught.exception.code, "privileged_helper_unavailable")


if __name__ == "__main__":
    unittest.main()
