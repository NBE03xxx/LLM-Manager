import tempfile
import unittest
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure.audit import LocalAuditLog
from llm_manager.infrastructure.redaction import REDACTED


class LocalAuditLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "audit"
        self.audit = LocalAuditLog(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_appends_reloads_and_redacts_hash_chain(self) -> None:
        self.audit.append("apply.started", "plan-1", (("host_id", "host-1"), ("api_token", "never-store"), ("error", "password=hunter2")))
        self.audit.append("apply.committed", "plan-1", (("duration_ms", 12),))
        events = LocalAuditLog(self.root).read_all()
        self.assertEqual([item.sequence for item in events], [1, 2])
        self.assertEqual(dict(events[0].fields)["api_token"], REDACTED)
        self.assertNotIn("hunter2", self.root.joinpath("00000000000000000001.json").read_text(encoding="utf-8"))
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root / "HEAD").stat().st_mode & 0o777, 0o600)

    def test_rejects_raw_content_fields(self) -> None:
        with self.assertRaises(AdapterError):
            self.audit.append("apply", "plan", (("config_content", "secret"),))

    def test_detects_event_tamper(self) -> None:
        self.audit.append("one", "plan", ())
        self.audit.append("two", "plan", ())
        first = self.root / "00000000000000000001.json"
        first.write_text(first.read_text(encoding="utf-8").replace('"event_type":"one"', '"event_type":"bad"'), encoding="utf-8")
        with self.assertRaises(AdapterError):
            self.audit.read_all()

    def test_detects_tail_deletion_against_head(self) -> None:
        self.audit.append("one", "plan", ())
        self.audit.append("two", "plan", ())
        (self.root / "00000000000000000002.json").unlink()
        with self.assertRaises(AdapterError):
            self.audit.read_all()


if __name__ == "__main__":
    unittest.main()
