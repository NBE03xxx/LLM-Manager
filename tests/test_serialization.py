import unittest
from datetime import datetime

from llm_manager.domain.errors import InvariantViolation
from llm_manager.domain.serialization import make_envelope, to_primitive, validate_schema_version

from tests.fixtures import report


class SerializationTests(unittest.TestCase):
    def test_report_serializes_to_json_compatible_values(self) -> None:
        result = to_primitive(report())
        self.assertEqual(result["host"]["kind"], "local")
        self.assertEqual(result["ollama"]["version"], "0.33.2")
        self.assertIsInstance(result["started_at"], str)
        datetime.fromisoformat(result["started_at"])

    def test_envelope_contains_schema_and_kind(self) -> None:
        envelope = make_envelope("diagnostic_report", report())
        self.assertEqual(envelope["schema_version"], "1.0")
        self.assertEqual(envelope["kind"], "diagnostic_report")

    def test_unknown_major_is_rejected(self) -> None:
        with self.assertRaises(InvariantViolation):
            validate_schema_version("2.0")

    def test_malformed_version_is_rejected(self) -> None:
        with self.assertRaises(InvariantViolation):
            validate_schema_version("one")


if __name__ == "__main__":
    unittest.main()
