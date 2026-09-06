import unittest
from dataclasses import replace

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandResult
from llm_manager.infrastructure.root_restore_service import RootRestoreOllamaService, SYSTEMCTL, CURL

CONTENT = b'[Service]\nEnvironment="OLLAMA_FLASH_ATTENTION=0"\n'
SHOW = 'LoadState=loaded\nActiveState=active\nSubState=running\nEnvironment=OLLAMA_FLASH_ATTENTION=0 OLLAMA_HOST=127.0.0.1:11434\n'


class Runner:
    def __init__(self, hook=None):
        self.calls = []
        self.hook = hook
        self.show = SHOW
        self.version = '{"version":"0.33.2"}\n200'
        self.tags = '{"models":[]}\n200'

    def run(self, request, cancellation):
        self.calls.append(request)
        if request.argv[0] == SYSTEMCTL:
            output = self.show if request.argv[1] == 'show' else ''
        else:
            output = self.version if request.argv[-1].endswith('/api/version') else self.tags
        result = CommandResult(request.argv, 0, output, '', False, 1)
        return self.hook(self, request, result, cancellation) if self.hook else result


class RootRestoreServiceTests(unittest.TestCase):
    def test_fixed_commands_and_loopback_api_complete_validation(self):
        runner = Runner()
        self.assertTrue(RootRestoreOllamaService(runner).reload_restart_validate(CONTENT, CancellationToken()))
        self.assertEqual([r.argv[:2] for r in runner.calls], [(SYSTEMCTL, 'daemon-reload'), (SYSTEMCTL, 'restart'),
                         (SYSTEMCTL, 'show'), (CURL, '--disable'), (CURL, '--disable')])
        self.assertEqual(runner.calls[1].argv, (SYSTEMCTL, 'restart', 'ollama.service'))
        for call in runner.calls[3:]:
            self.assertIn('--noproxy', call.argv)
            self.assertNotIn('--location', call.argv)
            self.assertTrue(call.argv[-1].startswith('http://127.0.0.1:11434/api/'))
            self.assertEqual(call.timeout_ms, 4000)

    def test_validated_loopback_port_and_ipv6_are_used_without_name_resolution(self):
        for host, endpoint in (('localhost:12345', '127.0.0.1:12345'), ('[::1]:11434', '[::1]:11434')):
            runner = Runner()
            runner.show = SHOW.replace('127.0.0.1:11434', host)
            with self.subTest(host=host):
                self.assertTrue(RootRestoreOllamaService(runner).reload_restart_validate(CONTENT, CancellationToken()))
                self.assertEqual(runner.calls[-1].argv[-1], 'http://' + endpoint + '/api/tags')

    def test_external_invalid_and_credential_endpoints_never_reach_curl(self):
        for host in ('0.0.0.0:11434', 'example.com:11434', '127.0.0.1:0', '127.0.0.1:65536',
                     '127.0.0.1:11434/path', 'user@127.0.0.1:11434'):
            runner = Runner()
            runner.show = SHOW.replace('127.0.0.1:11434', host)
            with self.subTest(host=host):
                self.assertFalse(RootRestoreOllamaService(runner).reload_restart_validate(CONTENT, CancellationToken()))
                self.assertEqual(len(runner.calls), 3)

    def test_effective_environment_mismatch_and_inactive_service_fail(self):
        for show in (SHOW.replace('ATTENTION=0', 'ATTENTION=1'), SHOW.replace('active\n', 'inactive\n'),
                     SHOW.replace('running', 'failed'), SHOW + 'ActiveState=active\n', SHOW.replace('Environment=', 'Unknown=')):
            runner = Runner()
            runner.show = show
            with self.subTest(show=show):
                self.assertFalse(RootRestoreOllamaService(runner).reload_restart_validate(CONTENT, CancellationToken()))
                self.assertEqual(len(runner.calls), 3)

    def test_unsupported_restored_syntax_stops_before_restart(self):
        for content in (b'[Service]\nExecStart=/bin/anything\n', b'', b'\xff',
                        b'[Service]\nEnvironment="OLLAMA_HOST=%H:11434"\n', CONTENT + CONTENT):
            runner = Runner()
            with self.subTest(content=content):
                self.assertFalse(RootRestoreOllamaService(runner).reload_restart_validate(content, CancellationToken()))
                self.assertEqual(runner.calls, [])

    def test_quoted_or_ambiguous_environment_fails_closed(self):
        for value in ('"OLLAMA_FLASH_ATTENTION=0"', 'OLLAMA_FLASH_ATTENTION=0 OLLAMA_FLASH_ATTENTION=1', 'not_an_assignment'):
            runner = Runner()
            runner.show = SHOW.split('Environment=')[0] + 'Environment=' + value + '\n'
            with self.subTest(value=value):
                self.assertFalse(RootRestoreOllamaService(runner).reload_restart_validate(CONTENT, CancellationToken()))

    def test_redirect_http_error_malformed_json_and_unknown_version_fail(self):
        for output in ('{}\n302', '{}\n500', 'not-json\n200', '[]\n200', '{"version":"0.34.0"}\n200', '{}\n200'):
            runner = Runner()
            runner.version = output
            with self.subTest(output=output):
                self.assertFalse(RootRestoreOllamaService(runner).reload_restart_validate(CONTENT, CancellationToken()))
                self.assertEqual(len(runner.calls), 4)

    def test_missing_model_list_is_not_api_success(self):
        runner = Runner()
        runner.tags = '{"models":null}\n200'
        self.assertFalse(RootRestoreOllamaService(runner).reload_restart_validate(CONTENT, CancellationToken()))

    def test_timeout_nonzero_and_cancellation_stop_at_every_stage(self):
        for stage in range(1, 6):
            for mode in ('timeout', 'exit', 'cancel'):
                def hook(runner, request, result, token):
                    if len(runner.calls) == stage:
                        if mode == 'cancel': token.cancel()
                        elif mode == 'timeout': return replace(result, timed_out=True)
                        else: return replace(result, exit_code=1)
                    return result
                runner = Runner(hook)
                with self.subTest(stage=stage, mode=mode):
                    if mode == 'cancel':
                        with self.assertRaises(OperationCancelled):
                            RootRestoreOllamaService(runner).reload_restart_validate(CONTENT, CancellationToken())
                    else:
                        self.assertFalse(RootRestoreOllamaService(runner).reload_restart_validate(CONTENT, CancellationToken()))
                    self.assertEqual(len(runner.calls), stage)

    def test_removal_checks_remaining_service_environment_and_default_endpoint(self):
        runner = Runner()
        runner.show = SHOW.split('Environment=')[0] + 'Environment=\n'
        self.assertTrue(RootRestoreOllamaService(runner).reload_restart_validate(None, CancellationToken()))
        self.assertEqual(runner.calls[-1].argv[-1], 'http://127.0.0.1:11434/api/tags')
