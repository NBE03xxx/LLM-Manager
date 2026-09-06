"""Fixed system Ollama restart and bounded loopback validation; not dispatched."""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from llm_manager.application.ports import CancellationToken, CommandRequest
from .process import ProcessPolicy, SubprocessRunner
from .root_backup_evidence import _cancel
from llm_manager.planning.ollama import _KEYS

SYSTEMCTL = '/usr/bin/systemctl'
CURL = '/usr/bin/curl'


class RootRestoreOllamaService:
    def __init__(self, runner=None):
        self.runner = runner if runner is not None else SubprocessRunner(
            ProcessPolicy(frozenset({SYSTEMCTL, CURL}), max_output_bytes=1024 * 1024)
        )

    def reload_restart_validate(self, restored_content: bytes | None, cancellation: CancellationToken) -> bool:
        _cancel(cancellation)
        expected = _restored_settings(restored_content)
        if expected is None:
            return False
        for args in (('daemon-reload',), ('restart', 'ollama.service')):
            if self._run((SYSTEMCTL,) + args, 30000, cancellation) is None:
                return False
        output = self._run((SYSTEMCTL, 'show', 'ollama.service',
                            '--property=LoadState,ActiveState,SubState,Environment', '--no-pager'), 3000, cancellation)
        if output is None: return False
        properties = {}
        for line in output.splitlines():
            key, separator, value = line.partition('=')
            if not separator or key in properties: return False
            properties[key] = value
        if any(properties.get(key) != value for key, value in (
            ('LoadState', 'loaded'), ('ActiveState', 'active'), ('SubState', 'running'),
        )) or 'Environment' not in properties:
            return False
        # Only the literal format emitted for the supported values is accepted.
        # Do not guess at systemd quoting/escape semantics in privileged code.
        raw = properties['Environment']
        if any(character in raw for character in '\\"\'\x00\r'): return False
        environment = {}
        for item in raw.split():
            key, separator, value = item.partition('=')
            if not separator or key in environment: return False
            environment[key] = value
        if any(environment.get(key) != value for key, value in expected.items()): return False
        endpoint = _endpoint(environment.get('OLLAMA_HOST', '127.0.0.1:11434'))
        if endpoint is None: return False
        for path in ('/api/version', '/api/tags'):
            response = self._run((CURL, '--disable', '--silent', '--show-error', '--fail',
                                  '--noproxy', '*', '--proto', '=http', '--max-redirs', '0',
                                  '--max-time', '3', '--write-out', '\n%{http_code}', endpoint + path), 4000, cancellation)
            if response is None: return False
            body, separator, status = response.rpartition('\n')
            if not separator or status != '200': return False
            try: document = json.loads(body)
            except (ValueError, RecursionError): return False
            if not isinstance(document, dict): return False
            if path == '/api/version' and document.get('version') != '0.33.2': return False
            if path == '/api/tags' and not isinstance(document.get('models'), list): return False
        _cancel(cancellation)
        return True

    def _run(self, argv, timeout, cancellation):
        _cancel(cancellation)
        result = self.runner.run(CommandRequest(argv, timeout, 'root_restore.service'), cancellation)
        _cancel(cancellation)
        return result.stdout if result.exit_code == 0 and not result.timed_out else None


def _restored_settings(content):
    if content is None: return {}
    try: text = content.decode('utf-8')
    except (UnicodeError, AttributeError): return None
    section, settings = False, {}
    for line in text.split('\n'):
        if any(ord(char) < 32 and char != '\t' for char in line) or line.rstrip().endswith('\\'): return None
        if not line.strip() or line.lstrip().startswith(('#', ';')): continue
        if line == '[Service]' and not section:
            section = True
            continue
        match = re.fullmatch(r'Environment="([A-Z_]+)=([A-Za-z0-9_.:\[\]+-]+)"', line)
        if not section or match is None or match[1] not in _KEYS or match[1] in settings: return None
        settings[match[1]] = match[2]
    return settings if section else None


def _endpoint(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:127\.0\.0\.1|localhost|\[::1\]):[0-9]{1,5}', value): return None
    parsed = urlsplit('http://' + value)
    try: port = parsed.port
    except ValueError: return None
    if port is None or not 1 <= port <= 65535: return None
    # Avoid name resolution in the privileged validation path.
    host = '[::1]' if parsed.hostname == '::1' else '127.0.0.1'
    return f'http://{host}:{port}'
