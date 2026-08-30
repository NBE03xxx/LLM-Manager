from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from llm_manager.application.errors import AdapterError

from .remote_helper import RemoteRecoveryAttemptStore


@dataclass(frozen=True, slots=True)
class RemoteRecoveryRuntime:
    """Production user-state composition for remote recovery attempts."""

    state_root: Path
    attempts: RemoteRecoveryAttemptStore

    @classmethod
    def for_current_user(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        home: Path | None = None,
    ) -> "RemoteRecoveryRuntime":
        values = os.environ if environ is None else environ
        user_home = Path.home() if home is None else home
        if not user_home.is_absolute() or user_home == Path("/"):
            raise AdapterError("unsafe_user_state_root", "user home is unsafe")
        configured = values.get("XDG_STATE_HOME", "")
        configured_path = Path(configured) if configured else None
        base = (
            configured_path
            if configured_path is not None and configured_path.is_absolute()
            else user_home / ".local/state"
        )
        if base == Path("/"):
            raise AdapterError("unsafe_user_state_root", "XDG state root is unsafe")
        application_root = base / "llm-manager"
        application_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        _private_directory(application_root)
        state_root = application_root / "remote-recovery"
        state_root.mkdir(mode=0o700, exist_ok=True)
        _private_directory(state_root)
        return cls(state_root, RemoteRecoveryAttemptStore(state_root / "attempts"))


def _private_directory(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        raise AdapterError("unsafe_user_state_root", "application state root is unsafe")
    metadata = path.stat(follow_symlinks=False)
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise AdapterError(
            "unsafe_user_state_root", "application state root metadata is unsafe"
        )
