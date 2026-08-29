from __future__ import annotations

import os
import re
from collections.abc import Callable
from typing import Protocol

from llm_manager.application.errors import AdapterError

_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_ATTRIBUTES = {
    "application": "llm-manager",
    "purpose": "backup-encryption",
}


class SecretServiceBackend(Protocol):
    def load(self, key_reference: str) -> bytes | None: ...

    def store(self, key_reference: str, key: bytes) -> None: ...


class SecretServiceKeyProvider:
    def __init__(self, backend: SecretServiceBackend, random_bytes: Callable[[int], bytes] = os.urandom) -> None:
        self.backend = backend
        self.random_bytes = random_bytes

    def get_key(self, key_reference: str, key_scope: str) -> bytes:
        if key_scope != "local_secret_service" or not _REFERENCE.fullmatch(key_reference):
            raise AdapterError("invalid_key_reference", "Secret Service provider accepts only local validated key references")
        existing = self.backend.load(key_reference)
        if existing is not None:
            return _validate_key(existing)
        candidate = self.random_bytes(32)
        _validate_key(candidate)
        try:
            self.backend.store(key_reference, candidate)
        except AdapterError as error:
            if error.code != "key_already_exists":
                raise
            raced = self.backend.load(key_reference)
            if raced is None:
                raise AdapterError("secret_service_unavailable", "key creation raced but no key can be loaded") from error
            return _validate_key(raced)
        return candidate


class SecretStorageBackend:
    """SecretStorage binding adapter. Import and D-Bus connection are intentionally lazy."""

    def __init__(self, unlock_timeout: float = 120.0) -> None:
        try:
            import secretstorage  # type: ignore[import-not-found]
        except ImportError as error:
            raise AdapterError("secret_service_unavailable", "SecretStorage dependency is unavailable") from error
        try:
            connection = secretstorage.dbus_init()
            if not secretstorage.check_service_availability(connection):
                raise AdapterError("secret_service_unavailable", "Secret Service is unavailable on the session bus")
            collection = secretstorage.get_default_collection(connection)
            if collection.is_locked():
                dismissed = collection.unlock(timeout=unlock_timeout)
                if dismissed or collection.is_locked():
                    raise AdapterError("secret_service_cancelled", "Secret Service unlock was dismissed")
        except AdapterError:
            raise
        except TimeoutError as error:
            raise AdapterError("secret_service_timeout", "Secret Service unlock timed out") from error
        except Exception as error:
            raise _mapped_error(error, "Secret Service initialization failed") from error
        self._secretstorage = secretstorage
        self._connection = connection
        self._collection = collection

    def load(self, key_reference: str) -> bytes | None:
        attributes = _ATTRIBUTES | {"key-reference": key_reference}
        try:
            items = list(self._secretstorage.search_items(self._connection, attributes))
            if not items:
                return None
            if len(items) != 1:
                raise AdapterError("ambiguous_key", "multiple Secret Service keys match the reference")
            item = items[0]
            if item.is_locked():
                dismissed = item.unlock(timeout=120.0)
                if dismissed or item.is_locked():
                    raise AdapterError("secret_service_cancelled", "Secret Service item unlock was dismissed")
            return item.get_secret()
        except AdapterError:
            raise
        except TimeoutError as error:
            raise AdapterError("secret_service_timeout", "Secret Service item unlock timed out") from error
        except Exception as error:
            raise _mapped_error(error, "Secret Service key lookup failed") from error

    def store(self, key_reference: str, key: bytes) -> None:
        attributes = _ATTRIBUTES | {"key-reference": key_reference}
        try:
            if list(self._secretstorage.search_items(self._connection, attributes)):
                raise AdapterError("key_already_exists", "Secret Service key already exists")
            self._collection.create_item(
                "LLM-Manager backup encryption key",
                attributes,
                key,
                replace=False,
                content_type="application/octet-stream",
            )
        except AdapterError:
            raise
        except Exception as error:
            # A concurrent creator may have won after the lookup.
            try:
                if list(self._secretstorage.search_items(self._connection, attributes)):
                    raise AdapterError("key_already_exists", "Secret Service key was created concurrently") from error
            except AdapterError:
                raise
            except Exception:
                pass
            raise _mapped_error(error, "Secret Service key creation failed") from error


def _validate_key(key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) != 32:
        raise AdapterError("invalid_key", "Secret Service backup key must contain exactly 32 bytes")
    return key


def _mapped_error(error: Exception, message: str) -> AdapterError:
    if type(error).__name__ == "PromptDismissedException":
        return AdapterError("secret_service_cancelled", message)
    return AdapterError("secret_service_unavailable", message)
