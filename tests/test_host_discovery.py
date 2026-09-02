import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_manager.application.host_discovery import DiscoverHosts, OpenSshConfigAliases
from llm_manager.domain.enums import HostKind


class OpenSshConfigAliasesTests(unittest.TestCase):
    def test_lists_literal_aliases_without_wildcards_or_negation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            config.write_text(
                "Host development *.internal !blocked\n"
                "  HostName 192.0.2.1\n"
                "Host ai-server development\n",
                encoding="utf-8",
            )
            self.assertEqual(OpenSshConfigAliases(config).list_aliases(), ("ai-server", "development"))

    def test_reads_relative_include_globs_and_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            included = root / "conf.d"
            included.mkdir()
            (included / "a.conf").write_text("Host build-box\n", encoding="utf-8")
            (included / "b.conf").write_text("Host build-box gpu-box\n", encoding="utf-8")
            config = root / "config"
            config.write_text("Include conf.d/*.conf\nHost local-alias\n", encoding="utf-8")
            self.assertEqual(
                OpenSshConfigAliases(config).list_aliases(),
                ("build-box", "gpu-box", "local-alias"),
            )

    def test_missing_config_is_an_empty_remote_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(OpenSshConfigAliases(Path(directory) / "missing").list_aliases(), ())

    def test_rejects_oversize_and_invalid_quoting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            config.write_bytes(b"x" * (1024 * 1024 + 1))
            with self.assertRaisesRegex(ValueError, "too large"):
                OpenSshConfigAliases(config).list_aliases()
            config.write_text('Host "unterminated\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid quoting"):
                OpenSshConfigAliases(config).list_aliases()

    def test_discovery_places_local_first_and_does_not_connect(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch("platform.node", return_value="workstation"):
            config = Path(directory) / "config"
            config.write_text("Host remote\n", encoding="utf-8")
            result = DiscoverHosts(OpenSshConfigAliases(config)).execute()
        self.assertEqual([item.host_id for item in result], ["local:workstation", "ssh:remote"])
        self.assertEqual(result[0].kind, HostKind.LOCAL)
        self.assertEqual(result[1].ssh_alias, "remote")


if __name__ == "__main__":
    unittest.main()
