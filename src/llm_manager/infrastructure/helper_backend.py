from __future__ import annotations

import os
import stat
import subprocess
from collections.abc import Callable
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.planning.ollama import DROP_IN_PATH

from .backup import MAX_ITEM_BYTES, _atomic_write, _fsync_directory, _within
from .helper_protocol import OLLAMA_UNIT

SYSTEMCTL = "/usr/bin/systemctl"
ServiceRunner = Callable[[tuple[str, ...]], int]


class LocalSystemHelperBackend:
    """Root-side backend with no caller-controlled paths, argv, units, or metadata."""

    def __init__(
        self,
        *,
        root: Path = Path("/"),
        service_runner: ServiceRunner | None = None,
        sandbox: bool = False,
    ) -> None:
        self.root = root.absolute()
        self.sandbox = sandbox
        if self.root != Path("/") and not sandbox:
            raise ValueError("alternate helper root requires explicit sandbox mode")
        if not sandbox and os.geteuid() != 0:
            raise AdapterError("root_required", "packaged helper backend requires root")
        self.service_runner = service_runner or _run_service_command

    def read_file(self, target: str) -> bytes | None:
        path = self._target(target)
        if not path.exists() and not path.is_symlink():
            return None
        self._regular(path)
        if path.stat(follow_symlinks=False).st_size > MAX_ITEM_BYTES:
            raise AdapterError("item_too_large", "helper target exceeds 16 MiB")
        return path.read_bytes()

    def atomic_write(self, target: str, content: bytes, mode: int, uid: int, gid: int) -> None:
        if len(content) > MAX_ITEM_BYTES:
            raise AdapterError("item_too_large", "helper content exceeds 16 MiB")
        if (mode, uid, gid) != (0o644, 0, 0):
            raise AdapterError("invalid_metadata", "helper backend accepts only 0644 root:root")
        path = self._target(target)
        self._prepare_parent(path.parent)
        if path.exists() or path.is_symlink():
            self._regular(path)
        _atomic_write(path, content, mode)
        if not self.sandbox:
            os.chown(path, uid, gid, follow_symlinks=False)
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            _fsync_directory(path.parent)

    def remove_file(self, target: str) -> None:
        path = self._target(target)
        self._regular(path)
        path.unlink()
        _fsync_directory(path.parent)

    def daemon_reload(self) -> None:
        self._service((SYSTEMCTL, "daemon-reload"))

    def restart_unit(self, unit: str) -> None:
        if unit != OLLAMA_UNIT:
            raise AdapterError("unit_not_allowed", "helper backend unit is not allowlisted")
        self._service((SYSTEMCTL, "restart", OLLAMA_UNIT))

    def _target(self, target: str) -> Path:
        if target != DROP_IN_PATH:
            raise AdapterError("target_not_allowed", "helper backend target is not allowlisted")
        path = self.root / Path(DROP_IN_PATH).relative_to("/")
        if self.root.is_symlink() or not _within(path.parent.resolve(strict=False), self.root.resolve()):
            raise AdapterError("unsafe_target", "helper target escaped its fixed root")
        self._reject_parent_symlinks(path.parent)
        return path

    def _prepare_parent(self, parent: Path) -> None:
        if not parent.exists():
            parent.mkdir(mode=0o755)
            _fsync_directory(parent.parent)
        if parent.is_symlink() or not parent.is_dir():
            raise AdapterError("unsafe_target", "helper target parent is unsafe")
        metadata = parent.stat(follow_symlinks=False)
        if stat.S_IMODE(metadata.st_mode) & 0o022:
            raise AdapterError("unsafe_target", "helper target parent is group/world writable")
        if not self.sandbox and metadata.st_uid != 0:
            raise AdapterError("unsafe_target", "helper target parent is not root-owned")

    def _reject_parent_symlinks(self, parent: Path) -> None:
        relative = parent.relative_to(self.root)
        current = self.root
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise AdapterError("unsafe_target", "helper target parent contains a symlink")
            if not current.exists():
                break

    @staticmethod
    def _regular(path: Path) -> None:
        if path.is_symlink() or not path.is_file():
            raise AdapterError("unsafe_target", "helper target is not a regular file")

    def _service(self, argv: tuple[str, ...]) -> None:
        try:
            exit_code = self.service_runner(argv)
        except OSError as error:
            raise AdapterError("service_command_failed", "fixed systemctl command could not start") from error
        if exit_code != 0:
            raise AdapterError("service_command_failed", "fixed systemctl command failed")


def _run_service_command(argv: tuple[str, ...]) -> int:
    completed = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        timeout=30,
        check=False,
        env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": "/usr/bin:/bin"},
    )
    return completed.returncode
