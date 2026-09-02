from __future__ import annotations

import re
from dataclasses import dataclass

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandRequest
from llm_manager.infrastructure.process import SubprocessRunner

_ALIAS = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_.@:-]{0,254}")
_FINGERPRINT = re.compile(
    r"^debug\d+: Server host key: (?P<algorithm>\S+) (?P<fingerprint>SHA256:[A-Za-z0-9+/]{43})$",
    re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class OpenSshHostIdentity:
    alias: str
    hostname: str
    port: int
    host_key_alias: str | None
    algorithm: str
    fingerprint: str


@dataclass(slots=True)
class OpenSshHostIdentityResolver:
    runner: SubprocessRunner
    timeout_ms: int = 10_000

    def resolve(self, alias: str, cancellation: CancellationToken) -> OpenSshHostIdentity:
        _validate_alias(alias)
        if cancellation.cancelled:
            raise OperationCancelled("host identity resolution cancelled")
        effective = self.runner.run(
            CommandRequest(("ssh", "-G", "--", alias), self.timeout_ms, "ssh.identity.config"),
            cancellation,
        )
        if effective.timed_out:
            raise AdapterError("timeout", "OpenSSH effective config timed out")
        if effective.exit_code != 0:
            raise AdapterError("ssh_config_failed", "OpenSSH effective config failed")
        values = _parse_effective_config(effective.stdout)
        hostname = values.get("hostname")
        if not hostname:
            raise AdapterError("ssh_config_failed", "OpenSSH effective hostname is missing")
        try:
            port = int(values.get("port", "22"))
        except ValueError as error:
            raise AdapterError("ssh_config_failed", "OpenSSH effective port is invalid") from error
        if not 1 <= port <= 65535:
            raise AdapterError("ssh_config_failed", "OpenSSH effective port is invalid")

        probe = self.runner.run(
            CommandRequest(
                (
                    "ssh",
                    "-vv",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "StrictHostKeyChecking=yes",
                    "-o",
                    "UpdateHostKeys=no",
                    "-o",
                    "RemoteCommand=none",
                    "-o",
                    "RequestTTY=no",
                    "--",
                    alias,
                    "true",
                ),
                self.timeout_ms,
                "ssh.identity.probe",
            ),
            cancellation,
        )
        if probe.timed_out:
            raise AdapterError("timeout", "OpenSSH host identity probe timed out")
        if probe.exit_code != 0:
            raise AdapterError("host_identity_unverified", "OpenSSH host identity probe did not complete")
        matches = {(match.group("algorithm"), match.group("fingerprint")) for match in _FINGERPRINT.finditer(probe.stderr_redacted)}
        if len(matches) != 1:
            raise AdapterError("host_identity_unverified", "OpenSSH did not report one verified server host key")
        algorithm, fingerprint = matches.pop()
        return OpenSshHostIdentity(
            alias=alias,
            hostname=hostname,
            port=port,
            host_key_alias=values.get("hostkeyalias"),
            algorithm=algorithm,
            fingerprint=fingerprint,
        )


def _parse_effective_config(content: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in content.splitlines():
        key, separator, value = line.partition(" ")
        if separator and key and value:
            values.setdefault(key.lower(), value.strip())
    return values


def _validate_alias(alias: str) -> None:
    if alias.startswith("-") or _ALIAS.fullmatch(alias) is None:
        raise ValueError("invalid OpenSSH host alias")
