import unittest

from llm_manager.adapters.clients.opencode import OpenCodeReadOnlyAdapter, parse_jsonc
from llm_manager.adapters.fakes import FakeHostAdapter
from llm_manager.adapters.ollama.readonly import OllamaReadOnlyAdapter
from llm_manager.application.ports import CancellationToken, CommandResult

from tests.fixtures import host_info


def result(argv: tuple[str, ...], stdout: str, exit_code: int = 0) -> CommandResult:
    return CommandResult(argv, exit_code, stdout, "", False, 1)


class OllamaAdapterTests(unittest.TestCase):
    def test_rejects_non_loopback_automatic_endpoint(self) -> None:
        with self.assertRaises(ValueError):
            OllamaReadOnlyAdapter("http://example.com:11434")

    def test_parses_version_service_models_and_redacts_environment(self) -> None:
        commands = {
            ("ollama", "--version"): result(("ollama", "--version"), "ollama version is 0.33.2\n"),
            (
                "systemctl",
                "show",
                "ollama.service",
                "--property=LoadState,ActiveState,SubState,UnitFileState,FragmentPath,DropInPaths,Environment",
                "--no-pager",
            ): result(
                ("systemctl",),
                "LoadState=loaded\nActiveState=active\nSubState=running\nUnitFileState=enabled\n"
                "FragmentPath=/usr/lib/systemd/system/ollama.service\nDropInPaths=/etc/systemd/system/ollama.service.d/override.conf\n"
                "Environment=OLLAMA_HOST=127.0.0.1:11434 API_KEY=secret\n",
            ),
            ("curl", "--silent", "--show-error", "--max-time", "3.0", "http://127.0.0.1:11434/api/tags"): result(
                ("curl",),
                '{"models":[{"name":"qwen:test","digest":"abc","size":42,"details":{"family":"qwen","parameter_size":"7B","quantization_level":"Q4"}}]}',
            ),
            ("curl", "--silent", "--show-error", "--max-time", "3.0", "http://127.0.0.1:11434/api/ps"): result(
                ("curl",), '{"models":[{"name":"qwen:test","context_length":8192,"size_vram":40}]}',
            ),
        }
        info = OllamaReadOnlyAdapter().inspect(
            FakeHostAdapter(host_info(), command_results=commands), CancellationToken()
        )
        self.assertEqual(info.version, "0.33.2")
        self.assertEqual(info.models[0].quantization, "Q4")
        self.assertEqual(info.loaded_models[0].runtime_context, 8192)
        self.assertEqual(dict(info.environment)["API_KEY"], "<redacted>")

    def test_missing_binary_is_not_installed(self) -> None:
        argv = ("ollama", "--version")
        host = FakeHostAdapter(host_info(), command_results={argv: result(argv, "", 127)})
        self.assertFalse(OllamaReadOnlyAdapter().inspect(host, CancellationToken()).installed)

    def test_api_version_detects_running_installation_without_cli(self) -> None:
        version_argv = ("curl", "--silent", "--show-error", "--max-time", "3.0", "http://127.0.0.1:11434/api/version")
        systemd_argv = (
            "systemctl", "show", "ollama.service",
            "--property=LoadState,ActiveState,SubState,UnitFileState,FragmentPath,DropInPaths,Environment",
            "--no-pager",
        )
        tags_argv = ("curl", "--silent", "--show-error", "--max-time", "3.0", "http://127.0.0.1:11434/api/tags")
        ps_argv = ("curl", "--silent", "--show-error", "--max-time", "3.0", "http://127.0.0.1:11434/api/ps")
        host = FakeHostAdapter(
            host_info(),
            command_results={
                version_argv: result(version_argv, '{"version":"0.33.2"}'),
                systemd_argv: result(systemd_argv, "LoadState=loaded\nActiveState=active\nSubState=running\n"),
                tags_argv: result(tags_argv, '{"models":[]}'),
                ps_argv: result(ps_argv, '{"models":[]}'),
            },
        )
        info = OllamaReadOnlyAdapter().inspect(host, CancellationToken())
        self.assertTrue(info.installed)
        self.assertEqual(info.version, "0.33.2")
        self.assertNotIn(("ollama", "--version"), [call[1].argv for call in host.calls if call[0] == "execute_readonly"])

    def test_nonzero_version_command_with_version_text_is_installed(self) -> None:
        argv = ("ollama", "--version")
        host = FakeHostAdapter(
            host_info(),
            command_results={
                argv: CommandResult(argv, 1, "", "Warning: client version is 0.33.2", False, 1),
                (
                    "systemctl",
                    "show",
                    "ollama.service",
                    "--property=LoadState,ActiveState,SubState,UnitFileState,FragmentPath,DropInPaths,Environment",
                    "--no-pager",
                ): result(("systemctl",), "", 1),
                ("curl", "--silent", "--show-error", "--max-time", "3.0", "http://127.0.0.1:11434/api/tags"): result(("curl",), "{}"),
                ("curl", "--silent", "--show-error", "--max-time", "3.0", "http://127.0.0.1:11434/api/ps"): result(("curl",), "{}"),
            },
        )
        info = OllamaReadOnlyAdapter().inspect(host, CancellationToken())
        self.assertTrue(info.installed)
        self.assertEqual(info.version, "0.33.2")


class OpenCodeAdapterTests(unittest.TestCase):
    def test_jsonc_preserves_comment_markers_inside_strings(self) -> None:
        parsed = parse_jsonc('{"url":"http://localhost", // comment\n"timeout": 30,}')
        self.assertEqual(parsed, {"url": "http://localhost", "timeout": 30})

    def test_inspects_jsonc_configuration(self) -> None:
        config = "/home/test/.config/opencode/opencode.jsonc"
        argv = ("opencode", "--version")
        host = FakeHostAdapter(
            host_info(),
            files={
                config: b'{"provider":"ollama","model":"qwen", "providers":{"ollama":{"options":{"baseURL":"http://127.0.0.1:11434/v1","timeout":120}}}, "compaction":true}',
            },
            command_results={argv: result(argv, "1.18.25\n")},
        )
        info = OpenCodeReadOnlyAdapter((config,)).inspect(host, CancellationToken())
        self.assertEqual(info.version, "1.18.25")
        self.assertEqual(info.base_url, "http://127.0.0.1:11434/v1")
        self.assertTrue(info.ollama_compatible)
        self.assertIn(("compaction", True), info.context_settings)

    def test_detects_multiple_provider_schema_without_selecting_one(self) -> None:
        config = "/tmp/opencode.jsonc"
        argv = ("opencode", "--version")
        host = FakeHostAdapter(
            host_info(),
            files={
                config: b'{"provider":{"first":{"options":{"baseURL":"http://127.0.0.1:11434/v1"},"models":{"qwen":{}}},"second":{"models":{"gemma":{}}}},"compaction":{"auto":true,"reserved":1000}}',
            },
            command_results={argv: result(argv, "1.18.25")},
        )
        info = OpenCodeReadOnlyAdapter((config,)).inspect(host, CancellationToken())
        self.assertIsNone(info.provider)
        self.assertEqual(info.available_providers, ("first", "second"))
        self.assertEqual(info.available_models, ("first/qwen", "second/gemma"))
        self.assertIn(("compaction.auto", True), info.context_settings)
        self.assertNotIn("apiKey", dict(info.context_settings))

    def test_malformed_config_returns_warning(self) -> None:
        config = "/tmp/opencode.jsonc"
        argv = ("opencode", "--version")
        host = FakeHostAdapter(
            host_info(), files={config: b"{"}, command_results={argv: result(argv, "1.18.25")}
        )
        info = OpenCodeReadOnlyAdapter((config,)).inspect(host, CancellationToken())
        self.assertEqual(info.parse_warnings, ("opencode.config.parse_failed",))


if __name__ == "__main__":
    unittest.main()
