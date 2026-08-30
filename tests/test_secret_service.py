import unittest
from types import SimpleNamespace
from unittest.mock import patch

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure.secret_service import (
    SecretServiceKeyProvider, SecretStorageBackend,
)


class _Backend:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.stores = 0
        self.failure: AdapterError | None = None

    def load(self, key_reference: str) -> bytes | None:
        return self.values.get(key_reference)

    def store(self, key_reference: str, key: bytes) -> None:
        self.stores += 1
        if self.failure:
            raise self.failure
        self.values[key_reference] = key


class SecretServiceKeyProviderTests(unittest.TestCase):
    def test_generates_once_and_reuses_persisted_key(self) -> None:
        backend = _Backend()
        provider = SecretServiceKeyProvider(backend, lambda size: b"k" * size)
        first = provider.get_key("local-master-v1", "local_secret_service")
        second = provider.get_key("local-master-v1", "local_secret_service")
        self.assertEqual(first, b"k" * 32)
        self.assertEqual(second, first)
        self.assertEqual(backend.stores, 1)

    def test_concurrent_creation_loads_winning_key(self) -> None:
        backend = _Backend()
        backend.failure = AdapterError("key_already_exists", "race")
        original_store = backend.store

        def raced_store(key_reference, key):
            backend.values[key_reference] = b"w" * 32
            original_store(key_reference, key)

        backend.store = raced_store  # type: ignore[method-assign]
        provider = SecretServiceKeyProvider(backend, lambda size: b"k" * size)
        self.assertEqual(provider.get_key("local-master-v1", "local_secret_service"), b"w" * 32)

    def test_rejects_invalid_scope_reference_and_stored_key(self) -> None:
        backend = _Backend()
        provider = SecretServiceKeyProvider(backend)
        with self.assertRaises(AdapterError):
            provider.get_key("remote", "remote_root")
        with self.assertRaises(AdapterError):
            provider.get_key("../escape", "local_secret_service")
        backend.values["bad"] = b"short"
        with self.assertRaises(AdapterError):
            provider.get_key("bad", "local_secret_service")

    def test_backend_failure_never_returns_generated_key(self) -> None:
        backend = _Backend()
        backend.failure = AdapterError("secret_service_cancelled", "cancelled")
        provider = SecretServiceKeyProvider(backend, lambda size: b"k" * size)
        with self.assertRaisesRegex(AdapterError, "cancelled"):
            provider.get_key("local-master-v1", "local_secret_service")
        self.assertNotIn("local-master-v1", backend.values)


class SecretStorageBackendTests(unittest.TestCase):
    def test_missing_binding_is_stable_unavailable(self) -> None:
        original_import = __import__

        def importing(name, *args, **kwargs):
            if name == "secretstorage":
                raise ImportError("injected")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=importing):
            with self.assertRaises(AdapterError) as raised:
                SecretStorageBackend()
        self.assertEqual(raised.exception.code, "secret_service_unavailable")

    def test_backend_initializes_stores_and_loads_through_binding(self) -> None:
        items = []
        collection = _Collection(items)
        module = SimpleNamespace(
            dbus_init=lambda: object(),
            check_service_availability=lambda connection: True,
            get_default_collection=lambda connection: collection,
            search_items=lambda connection, attributes: tuple(
                item for item in items if item.attributes == attributes
            ),
        )
        with patch.dict("sys.modules", {"secretstorage": module}):
            backend = SecretStorageBackend()
            self.assertIsNone(backend.load("desktop-gate"))
            backend.store("desktop-gate", b"k" * 32)
            self.assertEqual(backend.load("desktop-gate"), b"k" * 32)
            with self.assertRaises(AdapterError) as raised:
                backend.store("desktop-gate", b"x" * 32)
        self.assertEqual(raised.exception.code, "key_already_exists")


class _Collection:
    def __init__(self, items):
        self.items = items

    def is_locked(self):
        return False

    def create_item(self, label, attributes, secret, **kwargs):
        self.items.append(_Item(attributes, secret))


class _Item:
    def __init__(self, attributes, secret):
        self.attributes = attributes
        self.secret = secret

    def is_locked(self):
        return False

    def get_secret(self):
        return self.secret


if __name__ == "__main__":
    unittest.main()
