"""Explicit provisioning only; key reads never create or replace a key."""
from __future__ import annotations

import fcntl
import hashlib
import os
import uuid
from collections.abc import Callable

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from .root_backup_evidence import RootBackupEvidenceReader, _ID, _cancel, _open_fixed_directory

KEY_DIRECTORY = '/var/lib/llm-manager/local-root-restore/keys'


def open_production_key_directory() -> int:
    return _open_fixed_directory(KEY_DIRECTORY)


class ProvisionLocalRootKey:
    def __init__(self, directory_fd: int, *, owner_uid: int = 0, owner_gid: int = 0,
                 random_bytes: Callable[[int], bytes] = os.urandom):
        self.fd = directory_fd
        self.reader = RootBackupEvidenceReader(directory_fd, owner_uid=owner_uid, owner_gid=owner_gid)
        self.random_bytes = random_bytes

    def execute(self, key_id: str, cancellation: CancellationToken) -> str:
        if not isinstance(key_id, str) or not _ID.fullmatch(key_id):
            raise AdapterError('invalid_root_key_id', 'invalid root key ID')
        _cancel(cancellation)
        self.reader._directory()
        lock = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=self.fd)
        try:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise AdapterError('root_key_store_busy', 'root key store is busy') from error
            if any(name.startswith(key_id + '.') for name in os.listdir(self.fd)):
                raise AdapterError('root_key_exists', 'key ID already exists or requires reconciliation')
            key = self.random_bytes(32)
            if not isinstance(key, bytes) or len(key) != 32:
                raise AdapterError('invalid_root_key_entropy', 'key generator returned invalid bytes')
            _cancel(cancellation)
            self._publish(key_id + '.key', key, cancellation)
            os.fsync(self.fd)
            self._publish(key_id + '.ready', hashlib.sha256(key).hexdigest().encode('ascii'), cancellation)
            os.fsync(self.fd)
            return key_id
        except OSError as error:
            raise AdapterError('root_key_provisioning_incomplete', 'key provisioning requires reconciliation') from error
        finally:
            os.close(lock)

    def _publish(self, name: str, data: bytes, cancellation: CancellationToken) -> None:
        temporary = name + '.' + uuid.uuid4().hex + '.pending'
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=self.fd)
        try:
            os.fchmod(fd, 0o600)
            remaining = memoryview(data)
            while remaining:
                _cancel(cancellation)
                count = os.write(fd, remaining)
                if count <= 0: raise OSError('short key write')
                remaining = remaining[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        _cancel(cancellation)
        os.link(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd, follow_symlinks=False)
        os.unlink(temporary, dir_fd=self.fd)
