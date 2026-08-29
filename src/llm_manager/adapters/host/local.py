from __future__ import annotations

import hashlib
import os
import platform
import pwd
from dataclasses import dataclass
from pathlib import Path

from llm_manager.application.errors import OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandRequest, CommandResult, FileStat
from llm_manager.domain.enums import HostKind
from llm_manager.domain.models import HostCapabilities, HostInfo
from llm_manager.infrastructure.process import SubprocessRunner


@dataclass(slots=True)
class LocalHostAdapter:
    runner: SubprocessRunner
    display_name: str = "Local host"

    def identify(self, cancellation: CancellationToken) -> HostInfo:
        _check_cancelled(cancellation)
        return HostInfo(
            host_id=f"local:{platform.node()}",
            kind=HostKind.LOCAL,
            display_name=self.display_name,
            capabilities=self.capabilities(),
            hostname=platform.node(),
            user=pwd.getpwuid(os.getuid()).pw_name,
            fingerprint=f"local:{platform.node()}",
        )

    def capabilities(self) -> HostCapabilities:
        return HostCapabilities(
            can_execute=True,
            can_read_files=True,
            can_stage_files=False,
            can_elevate=False,
            service_manager="systemd" if Path("/run/systemd/system").exists() else None,
        )

    def execute_readonly(self, request: CommandRequest, cancellation: CancellationToken) -> CommandResult:
        return self.runner.run(request, cancellation)

    def stat(self, path: str, cancellation: CancellationToken) -> FileStat:
        _check_cancelled(cancellation)
        item = Path(path)
        try:
            stat = item.lstat()
        except FileNotFoundError:
            return FileStat(path=path, exists=False)
        content_hash = None
        if item.is_file() and not item.is_symlink():
            digest = hashlib.sha256()
            with item.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            content_hash = digest.hexdigest()
        return FileStat(
            path=path,
            exists=True,
            sha256=content_hash,
            mode=stat.st_mode & 0o7777,
            uid=stat.st_uid,
            gid=stat.st_gid,
            is_symlink=item.is_symlink(),
        )

    def read_file(self, path: str, max_bytes: int, cancellation: CancellationToken) -> bytes:
        _check_cancelled(cancellation)
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        item = Path(path)
        with item.open("rb") as handle:
            content = handle.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ValueError("file exceeds max_bytes")
        return content


def _check_cancelled(cancellation: CancellationToken) -> None:
    if cancellation.cancelled:
        raise OperationCancelled("operation cancelled")
