from __future__ import annotations

import json
import os
import pwd
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken

from .remote_backup import SandboxRemoteRecoveryStore
from .remote_helper_executor import RemoteRecoveryHelperExecutor
from .backup import _within


REMOTE_USER_ROOT = PurePosixPath(".local/state/llm-manager/remote-helper")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


def run_remote_helper(
    argv: tuple[str, ...],
    *,
    environ: Mapping[str, str] | None = None,
    effective_uid: int | None = None,
    current_uid: int | None = None,
    home_for_uid: Callable[[int], Path] | None = None,
    backend: SandboxRemoteRecoveryStore | None = None,
    cancellation: CancellationToken | None = None,
) -> tuple[int, bytes]:
    env = os.environ if environ is None else environ
    euid = os.geteuid() if effective_uid is None else effective_uid
    uid = os.getuid() if current_uid is None else current_uid
    home_lookup = home_for_uid or (lambda value: Path(pwd.getpwuid(value).pw_dir))
    token = cancellation or CancellationToken()
    try:
        if len(argv) == 2 and argv[0] in {"user-stage-prepare", "user-stage-remove"}:
            if euid != uid or euid == 0:
                raise AdapterError("invalid_remote_user", "user staging command requires an unprivileged user")
            home = _safe_home(home_lookup(uid))
            relative = _operation_relative(argv[1])
            if argv[0] == "user-stage-prepare":
                _prepare(home, relative, uid)
            else:
                _cleanup(home, relative, uid)
            return 0, _result(True, argv[0])
        if len(argv) == 3 and argv[0] == "invoke-recovery":
            if euid != 0:
                raise AdapterError("root_required", "remote recovery invocation requires root")
            invoking_uid = _invoking_uid(env)
            request_id, request_hash = argv[1:]
            if not _IDENTIFIER.fullmatch(request_id) or not _DIGEST.fullmatch(request_hash):
                raise AdapterError("invalid_remote_invocation", "remote recovery identity is invalid")
            if backend is None:
                raise AdapterError("remote_backend_unavailable", "remote recovery backend is unavailable")
            home = _safe_home(home_lookup(invoking_uid))
            staging_root = home / Path(REMOTE_USER_ROOT.as_posix())
            RemoteRecoveryHelperExecutor(
                staging_root, backend, invoking_uid
            ).execute(request_id, request_hash, token)
            return 0, _result(True, "invoke-recovery")
        raise AdapterError("invalid_remote_command", "remote helper command is not allowlisted")
    except OperationCancelled:
        return 2, _result(False, "cancelled")
    except (AdapterError, OSError, KeyError, ValueError) as error:
        return 1, _result(False, getattr(error, "code", "remote_helper_failed"))


def _operation_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    prefix = REMOTE_USER_ROOT.parts
    if (
        path.is_absolute() or path.parts[: len(prefix)] != prefix
        or len(path.parts) != len(prefix) + 2
        or not _IDENTIFIER.fullmatch(path.parts[-2])
        or not _DIGEST.fullmatch(path.parts[-1])
    ):
        raise AdapterError("invalid_remote_staging_path", "remote staging path is not a fixed operation path")
    return path


def _safe_home(home: Path) -> Path:
    result = home.absolute()
    if result == Path("/") or result.is_symlink() or not result.is_dir():
        raise AdapterError("unsafe_remote_home", "remote user home is unsafe")
    return result


def _prepare(home: Path, relative: PurePosixPath, uid: int) -> None:
    llm_root = home / ".local/state/llm-manager"
    llm_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not _within(llm_root.resolve(), home.resolve()):
        raise AdapterError("unsafe_remote_staging", "remote staging root escaped user home")
    _private_directory(llm_root, uid)
    current = llm_root
    suffix = relative.parts[len(PurePosixPath(".local/state/llm-manager").parts):]
    for part in (*suffix, "items"):
        current /= part
        current.mkdir(mode=0o700, exist_ok=True)
        _private_directory(current, uid)


def _cleanup(home: Path, relative: PurePosixPath, uid: int) -> None:
    directory = home / Path(relative.as_posix())
    if not _within(directory.resolve(), home.resolve()):
        raise AdapterError("unsafe_remote_staging", "remote staging path escaped user home")
    _private_directory(directory, uid)
    allowed = {"items", "request.json", "result.json"}
    if {path.name for path in directory.iterdir()} - allowed:
        raise AdapterError("unsafe_remote_staging", "unexpected staging entry prevents cleanup")
    items = directory / "items"
    _private_directory(items, uid)
    for path in items.iterdir():
        _private_file(path, uid)
    for name in ("request.json", "result.json"):
        path = directory / name
        if path.exists() or path.is_symlink():
            _private_file(path, uid)
    for path in items.iterdir():
        path.unlink()
    items.rmdir()
    for name in ("request.json", "result.json"):
        path = directory / name
        if path.exists():
            path.unlink()
    directory.rmdir()


def _private_directory(path: Path, uid: int) -> None:
    if path.is_symlink() or not path.is_dir():
        raise AdapterError("unsafe_remote_staging", "remote staging directory is unsafe")
    metadata = path.stat(follow_symlinks=False)
    if metadata.st_uid != uid or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise AdapterError("unsafe_remote_staging", "remote staging directory owner or mode is unsafe")


def _private_file(path: Path, uid: int) -> None:
    if path.is_symlink() or not path.is_file():
        raise AdapterError("unsafe_remote_staging", "remote staging file is unsafe")
    metadata = path.stat(follow_symlinks=False)
    if metadata.st_uid != uid or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise AdapterError("unsafe_remote_staging", "remote staging file owner or mode is unsafe")


def _invoking_uid(environ: Mapping[str, str]) -> int:
    value = environ.get("SUDO_UID", "")
    if not value.isascii() or not value.isdecimal():
        raise AdapterError("invalid_remote_user", "SUDO_UID is required")
    uid = int(value)
    if uid <= 0:
        raise AdapterError("invalid_remote_user", "invoking UID must be unprivileged")
    return uid


def _result(success: bool, code: str) -> bytes:
    return (json.dumps({"code": code, "success": success}, sort_keys=True, separators=(",", ":")) + "\n").encode()
