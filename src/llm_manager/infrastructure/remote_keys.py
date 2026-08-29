from __future__ import annotations

import os
import re
import stat
from collections.abc import Callable
from pathlib import Path

from llm_manager.application.errors import AdapterError

from .backup import _fsync_directory, _within


REMOTE_KEY_ROOT = Path("/var/lib/llm-manager/keys")
_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class RemoteRootKeyProvider:
    """Root-only persistent AES key provider, separated from backup content."""

    def __init__(
        self,
        root: Path = REMOTE_KEY_ROOT,
        *,
        sandbox: bool = False,
        effective_uid: int | None = None,
        owner_uid: int | None = None,
        random_bytes: Callable[[int], bytes] = os.urandom,
    ) -> None:
        self.root = root.absolute()
        self.sandbox = sandbox
        self.effective_uid = os.geteuid() if effective_uid is None else effective_uid
        self.owner_uid = (os.getuid() if sandbox else 0) if owner_uid is None else owner_uid
        self.random_bytes = random_bytes
        if self.root != REMOTE_KEY_ROOT and not sandbox:
            raise ValueError("alternate remote key root requires sandbox mode")
        if self.root == Path("/") or self.root.is_symlink():
            raise ValueError("remote key root is unsafe")

    def get_key(self, key_reference: str, key_scope: str) -> bytes:
        if key_scope != "remote_root" or not _REFERENCE.fullmatch(key_reference):
            raise AdapterError("invalid_key_reference", "remote key reference or scope is invalid")
        if not self.sandbox and self.effective_uid != 0:
            raise AdapterError("root_required", "remote root key access requires root")
        self._prepare_root()
        path = self.root / f"{key_reference}.key"
        if not _within(path.resolve(strict=False), self.root.resolve()):
            raise AdapterError("unsafe_remote_key", "remote key path escaped its root")
        if path.exists() or path.is_symlink():
            return self._load(path)
        candidate = self.random_bytes(32)
        _validate_key(candidate)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            return self._load(path)
        try:
            written = 0
            while written < len(candidate):
                count = os.write(descriptor, candidate[written:])
                if count <= 0:
                    raise OSError("remote key write made no progress")
                written += count
            os.fsync(descriptor)
        except Exception:
            # An incomplete O_EXCL file is deliberately retained and will fail
            # validation rather than silently rotating the recovery key.
            raise
        finally:
            os.close(descriptor)
        _fsync_directory(self.root)
        return self._load(path)

    def _prepare_root(self) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise AdapterError("unsafe_remote_key_root", "remote key root is unsafe")
        metadata = self.root.stat(follow_symlinks=False)
        if stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != self.owner_uid:
            raise AdapterError("unsafe_remote_key_root", "remote key root owner or mode is unsafe")

    def _load(self, path: Path) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise AdapterError("unsafe_remote_key", "remote key is missing or unsafe") from error
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != self.owner_uid
                or metadata.st_size != 32
            ):
                raise AdapterError("unsafe_remote_key", "remote key owner, mode, or size is unsafe")
            key = os.read(descriptor, 33)
        finally:
            os.close(descriptor)
        return _validate_key(key)


def _validate_key(key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) != 32:
        raise AdapterError("invalid_remote_key", "remote AES key must contain exactly 32 bytes")
    return key
