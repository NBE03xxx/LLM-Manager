from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from llm_manager.application.errors import AdapterError

from .backup_evidence_retention import BackupEvidenceRetentionExecutionStore
from .backup_evidence_retention_cleanup import (
    BackupEvidenceRetentionCleanupPort,
    BackupEvidenceRetentionCleanupRequestStore,
    BackupEvidenceRetentionCleanupService,
)


@dataclass(frozen=True, slots=True)
class BackupEvidenceRetentionRuntime:
    """Production user-state composition for retention execution evidence."""

    state_root: Path
    executions: BackupEvidenceRetentionExecutionStore
    cleanup_requests: BackupEvidenceRetentionCleanupRequestStore

    @classmethod
    def for_current_user(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        home: Path | None = None,
    ) -> "BackupEvidenceRetentionRuntime":
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
        _validate_private_directory(application_root)
        state_root = application_root / "backup-evidence-retention"
        state_root.mkdir(mode=0o700, exist_ok=True)
        _validate_private_directory(state_root)
        return cls(
            state_root,
            BackupEvidenceRetentionExecutionStore(state_root / "executions"),
            BackupEvidenceRetentionCleanupRequestStore(
                state_root / "cleanup-requests"
            ),
        )

    def cleanup_service(
        self, cleanup: BackupEvidenceRetentionCleanupPort,
    ) -> BackupEvidenceRetentionCleanupService:
        return BackupEvidenceRetentionCleanupService(
            self.executions, self.cleanup_requests, cleanup
        )


def _validate_private_directory(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        raise AdapterError("unsafe_user_state_root", "application state root is unsafe")
    metadata = path.stat(follow_symlinks=False)
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise AdapterError(
            "unsafe_user_state_root", "application state root metadata is unsafe"
        )
