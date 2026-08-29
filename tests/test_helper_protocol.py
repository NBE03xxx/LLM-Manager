import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure.helper_protocol import (
    HelperOperation, HelperOperationKind, HelperRequest, decode_request, encode_request,
)
from llm_manager.planning.ollama import DROP_IN_PATH


HASH = "a" * 64


def _request(now: datetime) -> HelperRequest:
    request = HelperRequest(
        1,
        "operation-1",
        "host-1",
        "plan-1",
        HASH,
        (
            HelperOperation("write-1", HelperOperationKind.ATOMIC_REPLACE, target=DROP_IN_PATH, before_hash=None, staged_content_hash=HASH, expected_mode=0o644, expected_uid=0, expected_gid=0),
            HelperOperation("reload-1", HelperOperationKind.DAEMON_RELOAD),
            HelperOperation("restart-1", HelperOperationKind.RESTART_UNIT, unit="ollama.service"),
        ),
        now,
        now + timedelta(minutes=5),
    )
    return request.with_hash()


class HelperProtocolTests(unittest.TestCase):
    def test_round_trip_accepts_only_canonical_bounded_request(self) -> None:
        now = datetime.now(UTC)
        request = _request(now)
        encoded = encode_request(request)
        self.assertEqual(decode_request(encoded, expected_hash=request.request_hash, now=now), request)

    def test_rejects_expired_future_and_overlong_requests(self) -> None:
        now = datetime.now(UTC)
        request = _request(now)
        with self.assertRaises(AdapterError):
            decode_request(encode_request(request), expected_hash=request.request_hash, now=now + timedelta(minutes=5))
        future = replace(request, requested_at=now + timedelta(seconds=1), expires_at=now + timedelta(minutes=2), request_hash="").with_hash()
        with self.assertRaises(AdapterError):
            decode_request(encode_request(future), expected_hash=future.request_hash, now=now)
        long = replace(request, expires_at=now + timedelta(minutes=11), request_hash="").with_hash()
        with self.assertRaises(AdapterError):
            encode_request(long)

    def test_rejects_hash_tamper_noncanonical_and_unknown_fields(self) -> None:
        now = datetime.now(UTC)
        request = _request(now)
        encoded = encode_request(request)
        with self.assertRaises(AdapterError):
            decode_request(encoded, expected_hash="b" * 64, now=now)
        value = json.loads(encoded)
        value["host_id"] = "other"
        tampered = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        with self.assertRaises(AdapterError):
            decode_request(tampered, expected_hash=request.request_hash, now=now)
        value = json.loads(encoded)
        value["shell"] = "/bin/sh"
        with self.assertRaises(AdapterError):
            decode_request(json.dumps(value, sort_keys=True, separators=(",", ":")).encode(), expected_hash=request.request_hash, now=now)

    def test_rejects_path_unit_and_operation_outside_allowlist(self) -> None:
        now = datetime.now(UTC)
        base = _request(now)
        invalid_operations = (
            replace(base.operations[0], target="/etc/passwd"),
            replace(base.operations[2], unit="ssh.service"),
            replace(base.operations[1], target=DROP_IN_PATH),
        )
        for operation in invalid_operations:
            request = replace(base, operations=(operation,), request_hash="").with_hash()
            with self.subTest(operation=operation):
                with self.assertRaises(AdapterError):
                    encode_request(request)

    def test_rejects_unsafe_file_metadata_and_unconditional_remove(self) -> None:
        now = datetime.now(UTC)
        base = _request(now)
        invalid_operations = (
            replace(base.operations[0], expected_mode=0o666),
            replace(base.operations[0], expected_uid=1000),
            HelperOperation(
                "remove-1", HelperOperationKind.REMOVE_CREATED_FILE,
                target=DROP_IN_PATH, before_hash=None,
            ),
        )
        for operation in invalid_operations:
            request = replace(base, operations=(operation,), request_hash="").with_hash()
            with self.subTest(operation=operation):
                with self.assertRaises(AdapterError):
                    encode_request(request)


if __name__ == "__main__":
    unittest.main()
