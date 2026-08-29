import json
import unittest

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher, MAX_PLAINTEXT_BYTES


class _Keys:
    def __init__(self, key: bytes = b"k" * 32) -> None:
        self.key = key
        self.calls: list[tuple[str, str]] = []

    def get_key(self, key_reference: str, key_scope: str) -> bytes:
        self.calls.append((key_reference, key_scope))
        return self.key


class BackupCryptoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.keys = _Keys()
        self.cipher = AesGcmBackupCipher(self.keys)
        self.arguments = {
            "backup_id": "backup-1",
            "host_fingerprint": "SHA256:host",
            "target": "/tmp/config",
            "key_reference": "local-master-v1",
            "key_scope": "local_secret_service",
        }

    def test_round_trip_uses_unique_nonce_and_does_not_store_key(self) -> None:
        first = self.cipher.encrypt(b"secret config", **self.arguments)
        second = self.cipher.encrypt(b"secret config", **self.arguments)
        self.assertNotEqual(json.loads(first)["nonce"], json.loads(second)["nonce"])
        self.assertNotIn((b"k" * 32), first)
        plaintext = self.cipher.decrypt(
            first,
            backup_id="backup-1",
            host_fingerprint="SHA256:host",
            target="/tmp/config",
            expected_key_reference="local-master-v1",
            expected_key_scope="local_secret_service",
        )
        self.assertEqual(plaintext, b"secret config")

    def test_aad_key_and_ciphertext_tampering_are_rejected(self) -> None:
        encrypted = self.cipher.encrypt(b"secret config", **self.arguments)
        decrypt = {
            "backup_id": "backup-1",
            "host_fingerprint": "SHA256:host",
            "target": "/tmp/config",
            "expected_key_reference": "local-master-v1",
            "expected_key_scope": "local_secret_service",
        }
        with self.assertRaises(AdapterError):
            self.cipher.decrypt(encrypted, **(decrypt | {"target": "/tmp/other"}))
        with self.assertRaises(AdapterError):
            self.cipher.decrypt(encrypted, **(decrypt | {"expected_key_reference": "other"}))
        envelope = json.loads(encrypted)
        envelope["ciphertext"] = envelope["ciphertext"][:-2] + "AA"
        tampered = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("ascii")
        with self.assertRaises(AdapterError):
            self.cipher.decrypt(tampered, **decrypt)

    def test_rejects_wrong_key_nonce_and_oversize(self) -> None:
        with self.assertRaises(AdapterError):
            AesGcmBackupCipher(_Keys(b"short")).encrypt(b"x", **self.arguments)
        with self.assertRaises(AdapterError):
            AesGcmBackupCipher(self.keys, lambda size: b"short").encrypt(b"x", **self.arguments)
        with self.assertRaises(AdapterError):
            self.cipher.encrypt(b"x" * (MAX_PLAINTEXT_BYTES + 1), **self.arguments)


if __name__ == "__main__":
    unittest.main()
