"""Privileged origin capture and marker-last publication, not yet dispatched.

All borrowed directory FDs must be securely anchored by privileged composition.
No user plaintext/manifest import or automatic key provisioning is supported.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import utc_now
from llm_manager.domain.serialization import to_primitive
from llm_manager.planning.ollama import DROP_IN_PATH
from .backup_crypto import AesGcmBackupCipher, MAX_PLAINTEXT_BYTES
from .helper_protocol import HelperOperationKind, HelperRequest, validate_request
from .local_root_restore_protocol import RootRestoreFileState
from .root_backup_evidence import (
    RootBackupEvidence, RootBackupEvidenceReader, _ID, _cancel, _identity,
    encode_evidence,
)


class LocalRootBackupKeys:
    """Read existing 32-byte keys from an anchored root:root 0700 directory."""

    def __init__(self, directory_fd: int, *, owner_uid: int = 0, owner_gid: int = 0):
        self.reader = RootBackupEvidenceReader(directory_fd, owner_uid=owner_uid, owner_gid=owner_gid)

    def get_key(self, key_reference: str, key_scope: str) -> bytes:
        lock = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=self.reader.directory_fd)
        try:
            try:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except OSError as error:
                raise AdapterError('root_key_store_busy', 'root key store is busy') from error
            return self._get_key(key_reference, key_scope)
        finally:
            os.close(lock)

    def _get_key(self, key_reference: str, key_scope: str) -> bytes:
        if key_scope != "local_root" or not isinstance(key_reference, str) or not _ID.fullmatch(key_reference):
            _reject("invalid_root_backup_key")
        try:
            self.reader._directory()
            if any(name.startswith(key_reference + '.') and name.endswith('.pending') for name in os.listdir(self.reader.directory_fd)):
                _reject("root_backup_key_incomplete")
            key = self.reader._read_file(key_reference + '.key', 32, CancellationToken())
            marker = self.reader._read_file(key_reference + '.ready', 64, CancellationToken())
            if marker != hashlib.sha256(key).hexdigest().encode('ascii'):
                _reject("invalid_root_backup_key")
            if len(key) != 32:
                _reject("invalid_root_backup_key")
            return key
        except OSError as error:
            raise AdapterError("root_backup_key_unavailable", "root backup key is unavailable") from error


class CaptureRootBackup:
    def __init__(
        self, store_fd: int, source_parent_fd: int, cipher: AesGcmBackupCipher,
        *, owner_uid: int = 0, owner_gid: int = 0, clock: Callable[[], datetime] = utc_now,
    ):
        self.store_fd = store_fd
        self.source_parent_fd = source_parent_fd
        self.cipher = cipher
        self.owner_uid, self.owner_gid = owner_uid, owner_gid
        self.clock = clock

    def execute(
        self, source: HelperRequest, *, expected_hash: str, key_id: str,
        cancellation: CancellationToken,
    ) -> RootBackupEvidence:
        _cancel(cancellation)
        validate_request(source, expected_hash, now=self.clock())
        files = [op for op in source.operations if op.target is not None]
        if (
            len(files) != 1 or files[0].kind is not HelperOperationKind.ATOMIC_REPLACE
            or source.backup_id is None or source.approval_id is None or source.manifest_hash is None
            or not isinstance(key_id, str) or not _ID.fullmatch(key_id)
        ):
            _reject("invalid_root_backup_capture")
        reader = RootBackupEvidenceReader(self.store_fd, owner_uid=self.owner_uid, owner_gid=self.owner_gid)
        reader._directory()
        lock_fd = None
        try:
            # A new open description is required: dup/shared borrowed FDs would
            # let concurrent callers silently convert each other's flock.
            lock_fd = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=self.store_fd)
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if lock_fd is not None:
                os.close(lock_fd)
            raise AdapterError("root_backup_store_busy", "root backup store is busy") from error
        try:
            prefix = source.backup_id
            # Any previous marker, payload or interrupted staging requires manual
            # reconciliation; never overwrite or retry an interrupted capture.
            if any(name.startswith(prefix + '.') for name in os.listdir(self.store_fd)):
                _reject("root_backup_capture_exists")
            observed = self._observe(cancellation)
            state, plaintext, _inode = observed
            if state.sha256 != files[0].before_hash:
                _reject("stale_root_backup_source")
            record = RootBackupEvidence(
                'llm-manager.root-backup-origin/1', prefix, source.host_id,
                source.request_hash, DROP_IN_PATH, state, None, None, self.clock(),
                source_manifest_hash=source.manifest_hash,
            )
            envelope = None
            if plaintext is not None:
                envelope = self.cipher.encrypt(
                    plaintext, backup_id=prefix, host_fingerprint=_aad_context(record),
                    target=DROP_IN_PATH, key_reference=key_id, key_scope='local_root',
                )
                record = replace(record, ciphertext_hash=hashlib.sha256(envelope).hexdigest(), key_id=key_id)
                if decrypt_root_backup(record.with_hash(), envelope, self.cipher) != plaintext:
                    _reject("root_backup_roundtrip_failed")
            _cancel(cancellation)
            validate_request(source, expected_hash, now=self.clock())
            if self._observe(cancellation) != observed:
                _reject("stale_root_backup_source")
            record = record.with_hash()
            encoded = encode_evidence(record)
            if envelope is not None:
                self._publish(prefix + '.bin', envelope, cancellation)
                os.fsync(self.store_fd)
            _cancel(cancellation)
            validate_request(source, expected_hash, now=self.clock())
            if self._observe(cancellation) != observed:
                _reject("stale_root_backup_source")
            reader._directory()
            self._publish(prefix + '.json', encoded, cancellation)
            os.fsync(self.store_fd)
            return record
        except OSError as error:
            raise AdapterError("root_backup_capture_incomplete", "root backup capture requires reconciliation") from error
        finally:
            os.close(lock_fd)

    def _observe(self, cancellation: CancellationToken):
        return observe_root_target(self.source_parent_fd, self.owner_uid, self.owner_gid, cancellation)

    def _publish(self, name: str, content: bytes, cancellation: CancellationToken) -> None:
        temporary = name + '.' + uuid.uuid4().hex + '.pending'
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=self.store_fd)
        try:
            os.fchmod(fd, 0o600)
            view = memoryview(content)
            while view:
                _cancel(cancellation)
                count = os.write(fd, view[:65536])
                if count <= 0: raise OSError('short write')
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        _cancel(cancellation)
        os.link(temporary, name, src_dir_fd=self.store_fd, dst_dir_fd=self.store_fd, follow_symlinks=False)
        os.unlink(temporary, dir_fd=self.store_fd)


def decrypt_root_backup(record: RootBackupEvidence, envelope: bytes, cipher: AesGcmBackupCipher) -> bytes:
    encode_evidence(record)
    if not record.original.exists or hashlib.sha256(envelope).hexdigest() != record.ciphertext_hash:
        _reject("invalid_root_backup_payload")
    plaintext = cipher.decrypt(
        envelope, backup_id=record.backup_id, host_fingerprint=_aad_context(record),
        target=record.target, expected_key_reference=record.key_id, expected_key_scope='local_root',
    )
    if hashlib.sha256(plaintext).hexdigest() != record.original.sha256:
        _reject("root_backup_plaintext_mismatch")
    return plaintext


def _aad_context(record: RootBackupEvidence) -> str:
    return json.dumps({
        'scope': 'local_root', 'host_id': record.host_id,
        'source_apply_request_hash': record.source_apply_request_hash,
        'source_manifest_hash': record.source_manifest_hash,
        'original': to_primitive(record.original),
    }, sort_keys=True, separators=(',', ':'))


def _reject(code: str) -> None:
    raise AdapterError(code, "root backup capture rejected")


def observe_root_target(parent_fd: int, owner_uid: int, owner_gid: int, cancellation: CancellationToken):
    _cancel(cancellation)
    parent = os.fstat(parent_fd)
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != owner_uid or parent.st_gid != owner_gid or stat.S_IMODE(parent.st_mode) & 0o022:
        _reject("unsafe_root_backup_source")
    name = DROP_IN_PATH.rsplit('/', 1)[1]
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent_fd)
    except FileNotFoundError:
        return RootRestoreFileState(False), None, None
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode) or before.st_uid != owner_uid
            or before.st_gid != owner_gid or stat.S_IMODE(before.st_mode) != 0o644
            or before.st_nlink != 1 or before.st_size > MAX_PLAINTEXT_BYTES
        ):
            _reject("unsafe_root_backup_source")
        data = bytearray()
        while len(data) <= MAX_PLAINTEXT_BYTES:
            _cancel(cancellation)
            chunk = os.read(fd, min(65536, MAX_PLAINTEXT_BYTES + 1 - len(data)))
            if not chunk: break
            data.extend(chunk)
        _cancel(cancellation)
        after = os.fstat(fd)
        linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if len(data) > MAX_PLAINTEXT_BYTES or _identity(before) != _identity(after) or _identity(after) != _identity(linked):
            _reject("stale_root_backup_source")
        return RootRestoreFileState(True, hashlib.sha256(data).hexdigest(), 0o644, 0, 0), bytes(data), _identity(after)
    finally:
        os.close(fd)
