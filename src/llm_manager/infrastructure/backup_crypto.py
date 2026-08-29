from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from llm_manager.application.errors import AdapterError

MAGIC = "LLM-MANAGER-BACKUP"
ALGORITHM = "AES-256-GCM"
ENVELOPE_VERSION = 1
MAX_PLAINTEXT_BYTES = 16 * 1024 * 1024
NONCE_BYTES = 12
TAG_BYTES = 16


class BackupKeyProvider(Protocol):
    def get_key(self, key_reference: str, key_scope: str) -> bytes: ...


class AesGcmBackupCipher:
    def __init__(self, keys: BackupKeyProvider, random_bytes: Callable[[int], bytes] = os.urandom) -> None:
        self.keys = keys
        self.random_bytes = random_bytes

    def encrypt(
        self,
        plaintext: bytes,
        *,
        backup_id: str,
        host_fingerprint: str | None,
        target: str,
        key_reference: str,
        key_scope: str,
    ) -> bytes:
        if len(plaintext) > MAX_PLAINTEXT_BYTES:
            raise AdapterError("item_too_large", "backup plaintext exceeds 16 MiB")
        key = self._key(key_reference, key_scope)
        nonce = self.random_bytes(NONCE_BYTES)
        if len(nonce) != NONCE_BYTES:
            raise AdapterError("invalid_nonce", "nonce source did not return 12 bytes")
        aad = _aad(backup_id, host_fingerprint, target)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
        envelope = {
            "algorithm": ALGORITHM,
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "key_reference": key_reference,
            "key_scope": key_scope,
            "magic": MAGIC,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "version": ENVELOPE_VERSION,
        }
        return json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("ascii")

    def decrypt(
        self,
        envelope_bytes: bytes,
        *,
        backup_id: str,
        host_fingerprint: str | None,
        target: str,
        expected_key_reference: str,
        expected_key_scope: str,
    ) -> bytes:
        try:
            envelope = json.loads(envelope_bytes.decode("ascii"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AdapterError("invalid_envelope", "backup envelope is not canonical JSON") from error
        required = {"algorithm", "ciphertext", "key_reference", "key_scope", "magic", "nonce", "version"}
        if not isinstance(envelope, dict) or set(envelope) != required:
            raise AdapterError("invalid_envelope", "backup envelope fields are invalid")
        if json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("ascii") != envelope_bytes:
            raise AdapterError("invalid_envelope", "backup envelope is not canonical")
        if envelope.get("magic") != MAGIC or envelope.get("version") != ENVELOPE_VERSION or envelope.get("algorithm") != ALGORITHM:
            raise AdapterError("unsupported_envelope", "backup envelope version or algorithm is unsupported")
        if envelope.get("key_reference") != expected_key_reference or envelope.get("key_scope") != expected_key_scope:
            raise AdapterError("key_scope_mismatch", "backup envelope key identity does not match the manifest")
        try:
            nonce = base64.b64decode(envelope["nonce"], validate=True)
            ciphertext = base64.b64decode(envelope["ciphertext"], validate=True)
        except (TypeError, ValueError) as error:
            raise AdapterError("invalid_envelope", "backup envelope encoding is invalid") from error
        if len(nonce) != NONCE_BYTES or not TAG_BYTES <= len(ciphertext) <= MAX_PLAINTEXT_BYTES + TAG_BYTES:
            raise AdapterError("invalid_envelope", "backup envelope sizes are invalid")
        key = self._key(expected_key_reference, expected_key_scope)
        try:
            return AESGCM(key).decrypt(nonce, ciphertext, _aad(backup_id, host_fingerprint, target))
        except InvalidTag as error:
            raise AdapterError("authentication_failed", "backup envelope authentication failed") from error

    def _key(self, key_reference: str, key_scope: str) -> bytes:
        if not key_reference or key_scope not in {"local_secret_service", "remote_root"}:
            raise AdapterError("invalid_key_reference", "backup key reference or scope is invalid")
        key = self.keys.get_key(key_reference, key_scope)
        if not isinstance(key, bytes) or len(key) != 32:
            raise AdapterError("invalid_key", "AES-256-GCM requires a 32-byte key")
        return key


def _aad(backup_id: str, host_fingerprint: str | None, target: str) -> bytes:
    if not backup_id or not target:
        raise AdapterError("invalid_aad", "backup ID and target are required")
    value = {
        "backup_id": backup_id,
        "envelope_version": ENVELOPE_VERSION,
        "host_fingerprint": host_fingerprint,
        "target": target,
    }
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
