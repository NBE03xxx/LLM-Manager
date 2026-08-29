import unittest

from llm_manager.adapters.fakes import FakeClientAdapter, FakeHostAdapter, FakeOllamaAdapter
from llm_manager.application.ports import CancellationToken
from llm_manager.application.validation import ProductRuntimeValidator
from llm_manager.domain.enums import ChangeOperation, ProbeStatus, ValidationStatus
from llm_manager.domain.models import Change, ChangeSet, OllamaInfo, OpenCodeInfo, ServiceInfo, ValidationResult
from tests.fixtures import host_info


def _result(check: str, passed: bool = True) -> ValidationResult:
    return ValidationResult(
        check,
        "runtime",
        check,
        ValidationStatus.PASSED if passed else ValidationStatus.FAILED,
    )


def _changes(*checks: str) -> ChangeSet:
    change = Change(
        "ollama-change",
        "/etc/systemd/system/ollama.service.d/90-llm-manager.conf",
        ChangeOperation.REPLACE_FILE,
        (),
        (("OLLAMA_HOST", "127.0.0.1:11434"),),
        "before",
        "diff",
        validation_checks=checks,
    )
    return ChangeSet("changes", "host-1", (change,), "hash")


class ProductRuntimeValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.host = FakeHostAdapter(host_info())
        self.client = FakeClientAdapter(OpenCodeInfo(installed=True))

    def test_validates_ollama_service_environment_and_api(self) -> None:
        ollama = FakeOllamaAdapter(
            OllamaInfo(
                installed=True,
                service=ServiceInfo("ollama.service", "loaded", "active", "running"),
                environment=(("OLLAMA_HOST", "127.0.0.1:11434"),),
                api_connectivity=ProbeStatus.OK,
            ),
            (_result("ollama.api.connectivity"),),
        )
        results = ProductRuntimeValidator(self.host, ollama, self.client).validate(
            _changes("ollama.service.active", "ollama.environment.effective", "ollama.api.connectivity"),
            CancellationToken(),
        )
        self.assertTrue(results)
        self.assertTrue(all(result.status is ValidationStatus.PASSED for result in results))
        self.assertEqual(ollama.calls, ["inspect", "validate_api"])

    def test_reports_effective_environment_mismatch(self) -> None:
        ollama = FakeOllamaAdapter(
            OllamaInfo(
                installed=True,
                service=ServiceInfo("ollama.service", "loaded", "active", "running"),
                environment=(("OLLAMA_HOST", "0.0.0.0:11434"),),
            )
        )
        results = ProductRuntimeValidator(self.host, ollama, self.client).validate(
            _changes("ollama.environment.effective"), CancellationToken()
        )
        self.assertEqual(results[0].status, ValidationStatus.FAILED)
        self.assertEqual(results[0].actual, "0.0.0.0:11434")

    def test_adapter_failure_becomes_failed_validation(self) -> None:
        ollama = FakeOllamaAdapter(OllamaInfo(installed=True), failure_code="inspect_failed")
        results = ProductRuntimeValidator(self.host, ollama, self.client).validate(
            _changes("ollama.service.active"), CancellationToken()
        )
        self.assertEqual(results[0].status, ValidationStatus.FAILED)
        self.assertEqual(results[0].actual, "inspect_failed")

    def test_delegates_opencode_runtime_validation(self) -> None:
        expected = _result("opencode.config.parse")
        client = FakeClientAdapter(OpenCodeInfo(installed=True), (expected,))
        results = ProductRuntimeValidator(
            self.host, FakeOllamaAdapter(OllamaInfo(installed=False)), client
        ).validate(_changes("opencode.config.parse"), CancellationToken())
        self.assertEqual(results, (expected,))
        self.assertEqual(client.calls, ["validate"])


if __name__ == "__main__":
    unittest.main()
