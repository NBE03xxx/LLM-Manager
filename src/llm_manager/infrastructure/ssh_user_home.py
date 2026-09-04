from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandRequest, HostPort


@dataclass(frozen=True, slots=True)
class RemoteUserHome:
    uid: int
    username: str
    home: str

    @property
    def opencode_candidates(self) -> tuple[str, ...]:
        root = PurePosixPath(self.home, ".config/opencode")
        return tuple(str(root / name) for name in ("opencode.jsonc", "opencode.json", "config.json"))

    def helper_target_map(self, targets: tuple[str, ...]) -> dict[str, str]:
        """Map exact diagnosed targets to the helper's fixed home-relative allowlist."""
        candidates = self.opencode_candidates
        if not targets or len(set(targets)) != len(targets):
            raise AdapterError(
                "ssh_user_config_not_allowed", "SSH user targets must be non-empty and unique"
            )
        if any(target not in candidates for target in targets):
            raise AdapterError(
                "ssh_user_config_not_allowed",
                "SSH user target is outside the remote user allowlist",
            )
        base = PurePosixPath(self.home)
        return {
            target: PurePosixPath(target).relative_to(base).as_posix()
            for target in targets
        }


@dataclass(frozen=True, slots=True)
class ResolveSshUserHome:
    timeout_ms: int = 10_000

    def execute(self, host: HostPort, cancellation: CancellationToken) -> RemoteUserHome:
        if cancellation.cancelled:
            raise OperationCancelled("SSH user home discovery cancelled")
        uid_result = host.execute_readonly(
            CommandRequest(("id", "-u"), self.timeout_ms, "ssh.user.uid"), cancellation
        )
        if uid_result.timed_out or uid_result.exit_code != 0:
            raise AdapterError("ssh_user_identity_unavailable", "remote UID could not be resolved")
        value = uid_result.stdout.strip()
        if not value.isascii() or not value.isdecimal() or int(value) <= 0:
            raise AdapterError("ssh_user_identity_invalid", "remote UID is invalid")
        uid = int(value)
        passwd = host.execute_readonly(
            CommandRequest(("getent", "passwd", str(uid)), self.timeout_ms, "ssh.user.passwd"),
            cancellation,
        )
        if passwd.timed_out or passwd.exit_code != 0:
            raise AdapterError("ssh_user_home_unavailable", "remote passwd entry could not be resolved")
        lines = passwd.stdout.splitlines()
        if len(lines) != 1:
            raise AdapterError("ssh_user_home_invalid", "remote passwd result is ambiguous")
        fields = lines[0].split(":")
        if len(fields) != 7 or fields[2] != str(uid):
            raise AdapterError("ssh_user_home_invalid", "remote passwd entry is invalid")
        username, home = fields[0], fields[5]
        path = PurePosixPath(home)
        if (
            not username
            or any(character in username for character in ":\r\n\x00")
            or not path.is_absolute()
            or path == PurePosixPath("/")
            or ".." in path.parts
            or any(character in home for character in "\r\n\x00")
        ):
            raise AdapterError("ssh_user_home_invalid", "remote user or home is unsafe")
        return RemoteUserHome(uid, username, path.as_posix())
