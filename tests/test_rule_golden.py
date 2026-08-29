import json
import unittest
from pathlib import Path

from llm_manager.domain.serialization import to_primitive
from llm_manager.optimization import AGENT, BALANCED, CODING, CATALOG_VERSION, RuleEngine, default_catalog

from tests.test_optimization import diagnostic


FIXTURES = Path(__file__).parent / "fixtures" / "rules"


class ProfileGoldenTests(unittest.TestCase):
    def test_profile_outputs_match_versioned_golden_files(self) -> None:
        manifest = json.loads((FIXTURES / "cases" / "profiles.json").read_text())
        self.assertEqual(manifest["catalog_version"], CATALOG_VERSION)
        profiles = {item.profile_id: item for item in (BALANCED, CODING, AGENT)}
        engine = RuleEngine(CATALOG_VERSION, default_catalog())
        for case in manifest["cases"]:
            with self.subTest(profile=case["profile"]):
                expected = json.loads((FIXTURES / "expected" / case["expected"]).read_text())
                actual = to_primitive(engine.evaluate(diagnostic(), profiles[case["profile"]]))
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
