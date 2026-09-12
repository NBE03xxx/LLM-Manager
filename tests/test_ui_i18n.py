import unittest

from llm_manager.ui.i18n import Catalog, select_locale


class UiI18nTests(unittest.TestCase):
    def test_selects_japanese_and_english_from_common_locale_forms(self) -> None:
        self.assertEqual(select_locale("ja_JP.UTF-8"), "ja")
        self.assertEqual(select_locale("en-US"), "en")

    def test_unsupported_and_empty_locale_fall_back_to_english(self) -> None:
        self.assertEqual(select_locale("fr_FR"), "en")
        self.assertEqual(select_locale(None), "en")

    def test_catalogs_have_identical_keys(self) -> None:
        self.assertEqual(Catalog.keys("en"), Catalog.keys("ja"))

    def test_unknown_message_key_falls_back_to_stable_key(self) -> None:
        self.assertEqual(Catalog("ja").text("unknown.key"), "unknown.key")

    def test_unsupported_catalog_uses_english(self) -> None:
        self.assertEqual(Catalog("de").locale, "en")
        self.assertEqual(Catalog("de").text("nav.hosts"), "Hosts")

    def test_local_root_apply_refusal_describes_pending_rule_not_composition(self) -> None:
        key = "apply.reason.local_root_apply_rule_pending"
        self.assertIn("actionable Ollama setting rule", Catalog("en").text(key))
        self.assertIn("Ollama設定ルール", Catalog("ja").text(key))
        self.assertNotIn("composition", Catalog("en").text(key))

    def test_apply_status_does_not_mislabel_production_as_sandbox(self) -> None:
        for locale in ("en", "ja"):
            for key in ("results.running", "results.completed", "results.failed"):
                with self.subTest(locale=locale, key=key):
                    message = Catalog(locale).text(key, status="rolled_back", error="validation failed")
                    self.assertNotIn("sandbox", message.lower())
                    self.assertIn("Apply", message)
                    if key != "results.running":
                        self.assertIn("rolled_back", message)
                    if key == "results.failed":
                        self.assertIn("validation failed", message)


if __name__ == "__main__":
    unittest.main()
