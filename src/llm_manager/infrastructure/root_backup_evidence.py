"""Read-only root backup evidence; no import, capture, decrypt, or restore API.

The privileged producer must capture original target bytes itself. Installing a
user-supplied manifest here is NOT an allowed way to create trusted evidence.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, replace
from datetime import datetime

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.serialization import to_primitive
from llm_manager.planning.ollama import DROP_IN_PATH
from .backup_crypto import MAX_ENVELOPE_BYTES
from .local_root_restore_protocol import RootRestoreFileState, _validate_file_state

STORE_PATH = "/var/lib/llm-manager/local-root-restore/backups"
MAX_RECORD_BYTES = 16 * 1024
MAX_CIPHERTEXT_BYTES = MAX_ENVELOPE_BYTES
MAX_INVENTORY_ITEMS = 32
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_HASH = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class RootBackupEvidence:
    schema: str
    backup_id: str
    host_id: str
    source_apply_request_hash: str
    target: str
    original: RootRestoreFileState
    ciphertext_hash: str | None
    key_id: str | None
    captured_at: datetime
    record_hash: str = ""
    source_manifest_hash: str = ""

    def with_hash(self) -> "RootBackupEvidence":
        value = replace(self, record_hash="")
        return replace(value, record_hash=hashlib.sha256(_canonical(value)).hexdigest())


@dataclass(frozen=True, slots=True)
class RootBackupInventoryItem:
    backup_id: str
    host_id: str
    captured_at: datetime
    original: RootRestoreFileState
    record_hash: str
    source_apply_request_hash: str
    source_manifest_hash: str


def encode_evidence(record: RootBackupEvidence) -> bytes:
    _validate(record)
    content = _canonical(record)
    if len(content) > MAX_RECORD_BYTES:
        _reject()
    return content


def decode_evidence(content: bytes) -> RootBackupEvidence:
    if len(content) > MAX_RECORD_BYTES:
        _reject()
    try:
        value = json.loads(content.decode("utf-8"))
        value["original"] = RootRestoreFileState(**value["original"])
        value["captured_at"] = datetime.fromisoformat(value["captured_at"])
        record = RootBackupEvidence(**value)
        canonical = _canonical(record)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as error:
        raise AdapterError("invalid_root_backup_evidence", "invalid root backup evidence") from error
    if canonical != content:
        _reject()
    _validate(record)
    return record


def _validate(record: RootBackupEvidence) -> None:
    if record.schema != "llm-manager.root-backup-origin/1" or record.target != DROP_IN_PATH:
        _reject()
    for value in (record.backup_id, record.host_id):
        if not isinstance(value, str) or not _ID.fullmatch(value):
            _reject()
    for value in (record.source_apply_request_hash, record.source_manifest_hash, record.record_hash):
        if not isinstance(value, str) or not _HASH.fullmatch(value):
            _reject()
    _validate_file_state(record.original)
    if record.original.exists:
        if not isinstance(record.ciphertext_hash, str) or not _HASH.fullmatch(record.ciphertext_hash):
            _reject()
        if not isinstance(record.key_id, str) or not _ID.fullmatch(record.key_id):
            _reject()
    elif record.ciphertext_hash is not None or record.key_id is not None:
        _reject()
    if not isinstance(record.captured_at, datetime) or record.captured_at.tzinfo is None or record.captured_at.utcoffset() is None:
        _reject()
    if record.with_hash() != record:
        _reject()


class RootBackupEvidenceReader:
    """Borrow a validated directory FD; never close it or create directories.

    The caller must securely anchor the directory. Production uses
    open_production_directory(), never a path supplied by a request. owner_uid
    is an explicit sandbox seam; privileged composition must use its default 0.
    """

    def __init__(self, directory_fd: int, *, owner_uid: int = 0, owner_gid: int = 0):
        self.directory_fd = directory_fd
        self.owner_uid = owner_uid
        self.owner_gid = owner_gid

    def read(
        self, backup_id: str, expected_hash: str, cancellation: CancellationToken,
    ) -> tuple[RootBackupEvidence, bytes | None]:
        if not isinstance(expected_hash, str) or not _HASH.fullmatch(expected_hash):
            _reject()
        return self._locked_read(backup_id, expected_hash, cancellation)

    def inspect(self, backup_id: str, cancellation: CancellationToken) -> tuple[RootBackupEvidence, bytes | None]:
        """Discover a root-owned origin; this is not mutation authorization."""
        return self._locked_read(backup_id, None, cancellation)

    def list_inventory(self, cancellation: CancellationToken) -> tuple[RootBackupInventoryItem, ...]:
        """Return a bounded, stable inventory or reject the whole unsafe store."""
        _cancel(cancellation)
        lock_fd = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
                          dir_fd=self.directory_fd)
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except OSError as error:
                raise AdapterError("root_backup_store_busy", "root backup store is busy") from error
            self._directory()
            before = frozenset(os.listdir(self.directory_fd))
            identifiers = sorted(name[:-5] for name in before if name.endswith('.json'))
            if (len(identifiers) > MAX_INVENTORY_ITEMS
                    or len(set(identifiers)) != len(identifiers)
                    or any(not _ID.fullmatch(value) for value in identifiers)):
                raise AdapterError('root_backup_inventory_too_large',
                                   'root backup inventory requires administrator review')
            records = tuple(self._read(value, None, cancellation)[0] for value in identifiers)
            expected = {record.backup_id + '.json' for record in records}
            expected.update(record.backup_id + '.bin' for record in records if record.original.exists)
            _cancel(cancellation)
            if before != frozenset(expected) or frozenset(os.listdir(self.directory_fd)) != before:
                raise AdapterError('unsafe_root_backup_inventory',
                                   'root backup inventory requires administrator review')
            return tuple(RootBackupInventoryItem(
                record.backup_id, record.host_id, record.captured_at, record.original,
                record.record_hash, record.source_apply_request_hash,
                record.source_manifest_hash,
            ) for record in records)
        except OSError as error:
            raise AdapterError('unsafe_root_backup_inventory',
                               'root backup inventory is unavailable or unsafe') from error
        finally:
            os.close(lock_fd)

    def _locked_read(self, backup_id, expected_hash, cancellation):
        _cancel(cancellation)
        lock_fd = None
        try:
            # A new open description is required: dup/shared borrowed FDs would
            # let concurrent callers silently convert each other's flock.
            lock_fd = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=self.directory_fd)
            fcntl.flock(lock_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError as error:
            if lock_fd is not None:
                os.close(lock_fd)
            raise AdapterError("root_backup_store_busy", "root backup store is busy") from error
        try:
            return self._read(backup_id, expected_hash, cancellation)
        finally:
            os.close(lock_fd)

    def _read(
        self, backup_id: str, expected_hash: str, cancellation: CancellationToken,
    ) -> tuple[RootBackupEvidence, bytes | None]:
        if not isinstance(backup_id, str) or not _ID.fullmatch(backup_id):
            _reject()
        if expected_hash is not None and (not isinstance(expected_hash, str) or not _HASH.fullmatch(expected_hash)):
            _reject()
        _cancel(cancellation)
        try:
            self._directory()
            name = backup_id + ".json"
            raw = self._read_file(name, MAX_RECORD_BYTES, cancellation)
            record = decode_evidence(raw)
            if record.backup_id != backup_id or (expected_hash is not None and record.record_hash != expected_hash):
                _reject()
            payload_name = backup_id + ".bin"
            payload = None
            if record.original.exists:
                payload = self._read_file(payload_name, MAX_CIPHERTEXT_BYTES, cancellation)
                if not payload or hashlib.sha256(payload).hexdigest() != record.ciphertext_hash:
                    _reject()
            else:
                try:
                    os.stat(payload_name, dir_fd=self.directory_fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    _reject()
            if self._read_file(name, MAX_RECORD_BYTES, cancellation) != raw:
                _reject()
            self._directory()
            _cancel(cancellation)
            return record, payload
        except OSError as error:
            raise AdapterError("unsafe_root_backup_store", "root backup evidence is unavailable or unsafe") from error

    def _directory(self) -> None:
        metadata = os.fstat(self.directory_fd)
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != self.owner_uid or metadata.st_gid != self.owner_gid or stat.S_IMODE(metadata.st_mode) != 0o700:
            _reject()

    def _read_file(self, name: str, limit: int, cancellation: CancellationToken) -> bytes:
        _cancel(cancellation)
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=self.directory_fd)
        try:
            before = os.fstat(fd)
            if (
                not stat.S_ISREG(before.st_mode) or before.st_uid != self.owner_uid or before.st_gid != self.owner_gid
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1
                or before.st_size > limit
            ):
                _reject()
            data = bytearray()
            while len(data) <= limit:
                _cancel(cancellation)
                chunk = os.read(fd, min(65536, limit + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            _cancel(cancellation)
            after = os.fstat(fd)
            linked = os.stat(name, dir_fd=self.directory_fd, follow_symlinks=False)
            if len(data) > limit or _identity(before) != _identity(after) or _identity(after) != _identity(linked):
                _reject()
            return bytes(data)
        finally:
            os.close(fd)


def open_production_directory() -> int:
    """Open fixed root-owned chain without following any symlink; no mkdir."""
    return _open_fixed_directory(STORE_PATH)


def _open_fixed_directory(path: str, *, private: bool = True) -> int:
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for component in path.strip("/").split("/"):
            metadata = os.fstat(fd)
            if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o022:
                _reject()
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
        if private:
            RootBackupEvidenceReader(fd)._directory()
        else:
            metadata = os.fstat(fd)
            if metadata.st_uid != 0 or metadata.st_gid != 0 or stat.S_IMODE(metadata.st_mode) & 0o022:
                _reject()
        return fd
    except BaseException:
        os.close(fd)
        raise


def _identity(value: os.stat_result) -> tuple[int, ...]:
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _cancel(token: CancellationToken) -> None:
    if token.cancelled:
        raise OperationCancelled("root backup evidence read cancelled")


def _canonical(value: object) -> bytes:
    return json.dumps(to_primitive(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _reject() -> None:
    raise AdapterError("invalid_root_backup_evidence", "root backup evidence rejected")
