from __future__ import annotations

import json
import os
from enum import StrEnum
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.domain.models import EncryptionInfo

from .backup import _atomic_write


class BuildMode(StrEnum):
    DEVELOPMENT = "development"
    DISTRIBUTION = "distribution"


def default_backup_policy(mode: BuildMode) -> EncryptionInfo:
    if mode is BuildMode.DEVELOPMENT:
        return EncryptionInfo(enabled=False)
    if mode is BuildMode.DISTRIBUTION:
        return _enabled_policy()
    raise AdapterError("invalid_build_mode", "unknown build mode")


class BackupSettingsStore:
    """Persists user choice; build mode affects only the initial default."""

    def __init__(self, path: Path) -> None:
        self.path = path.absolute()

    def load(self, mode: BuildMode) -> EncryptionInfo:
        if not self.path.exists():
            return default_backup_policy(mode)
        if self.path.is_symlink() or not self.path.is_file() or self.path.stat().st_size > 64 * 1024:
            raise AdapterError("invalid_backup_settings", "backup settings file is unsafe")
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AdapterError("invalid_backup_settings", "backup settings are malformed") from error
        if (
            not isinstance(value, dict)
            or set(value) != {"encryption_enabled", "schema_version"}
            or value.get("schema_version") != "1.0"
            or type(value.get("encryption_enabled")) is not bool
            or _bytes(bool(value["encryption_enabled"])) != self.path.read_bytes()
        ):
            raise AdapterError("invalid_backup_settings", "backup settings schema is invalid")
        return _enabled_policy() if value["encryption_enabled"] else EncryptionInfo(enabled=False)

    def save(self, policy: EncryptionInfo) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        _atomic_write(self.path, _bytes(policy.enabled), 0o600)


def _enabled_policy() -> EncryptionInfo:
    return EncryptionInfo(
        enabled=True,
        scheme="AES-256-GCM",
        envelope_version=1,
        key_reference="local-master-v1",
        key_scope="local_secret_service",
    )


def _bytes(enabled: bool) -> bytes:
    value = {"encryption_enabled": enabled, "schema_version": "1.0"}
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
