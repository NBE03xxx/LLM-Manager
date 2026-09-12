import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from llm_manager.domain.enums import ReportStatus


spec = importlib.util.spec_from_file_location(
    "ssh_measurement", Path(__file__).parents[1] / "packaging/measure-ssh-diagnosis.py"
)
measurement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measurement)


def report(fingerprint="SHA256:" + "a" * 43):
    return SimpleNamespace(
        host=SimpleNamespace(fingerprint=fingerprint), status=ReportStatus.PARTIAL,
        system=None, hardware=None, ollama=None, opencode=None,
        private_config="must not appear in evidence",
    )


class SshDiagnosisMeasurementTests(unittest.TestCase):
    def test_partial_samples_are_preserved_and_authentication_is_noninteractive(self):
        factory = Mock()
        factory.return_value.return_value = report()
        with patch.object(measurement.DiagnosticTaskFactory, "production", return_value=factory):
            result = measurement.measure("trusted-alias", 2)
        self.assertIsNone(factory.ssh_auth_broker)
        self.assertEqual(factory.call_count, 2)
        self.assertEqual([sample["status"] for sample in result["samples"]], ["partial"] * 2)
        self.assertNotIn("private_config", str(result))
        self.assertNotIn("trusted-alias", str(result))
        self.assertGreaterEqual(result["elapsed_max_ms"], result["elapsed_median_ms"])

    def test_missing_or_changed_identity_is_rejected(self):
        for identities in ((None,), ("SHA256:" + "a" * 43, "SHA256:" + "b" * 43)):
            with self.subTest(identities=identities):
                factory = Mock()
                factory.return_value.side_effect = [report(value) for value in identities]
                with patch.object(measurement.DiagnosticTaskFactory, "production", return_value=factory):
                    with self.assertRaisesRegex(ValueError, "identity"):
                        measurement.measure("trusted-alias", len(identities))

    def test_complete_report_does_not_imply_runtime_availability(self):
        observed = report()
        observed.status = ReportStatus.COMPLETE
        factory = Mock()
        factory.return_value.return_value = observed
        with patch.object(measurement.DiagnosticTaskFactory, "production", return_value=factory):
            result = measurement.measure("trusted-alias", 1)
        self.assertEqual(result["samples"][0]["status"], "complete")
        self.assertFalse(result["samples"][0]["runtime_prerequisites_available"])

    def test_invalid_arguments_fail_before_factory_creation(self):
        with patch.object(measurement.DiagnosticTaskFactory, "production") as factory:
            for alias, samples in (("-unsafe", 1), ("host;command", 1), ("valid", 0), ("valid", 21)):
                with self.subTest(alias=alias, samples=samples), self.assertRaises(ValueError):
                    measurement.measure(alias, samples)
            factory.assert_not_called()
