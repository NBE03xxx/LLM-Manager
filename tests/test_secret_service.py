import unittest

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure.secret_service import SecretServiceKeyProvider


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


if __name__ == "__main__":
    unittest.main()
