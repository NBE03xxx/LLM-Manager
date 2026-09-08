import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from llm_manager.application.errors import AdapterError
from llm_manager.application.restore_availability import AssessProductionRestoreAvailability
from llm_manager.domain.enums import HostKind
from llm_manager.infrastructure import helper_protocol
from llm_manager.infrastructure.local_root_restore_protocol import (
    PROTOCOL, MAX_REQUEST_BYTES, LocalRootRestoreRequest, RootRestoreFileState,
    decode_request, encode_request,
)
from llm_manager.planning.ollama import DROP_IN_PATH

NOW = datetime(2026, 9, 5, 10, tzinfo=UTC)


def request():
    return LocalRootRestoreRequest(
        PROTOCOL, 1, "restore-1", "local:host", 1000, "backup-1",
        "a" * 64, "b" * 64, "c" * 64, "approval-1", DROP_IN_PATH,
        RootRestoreFileState(True, "d" * 64, 0o644, 0, 0),
        RootRestoreFileState(True, "e" * 64, 0o644, 0, 0),
        NOW, NOW + timedelta(minutes=5),
    ).with_hash()


def decode(content, source=None, **overrides):
    source = source or request()
    args = dict(expected_hash=source.request_hash, expected_caller_uid=1000,
                expected_host_id="local:host", now=NOW)
    args.update(overrides)
    return decode_request(content, **args)


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class LocalRootRestoreProtocolTests(unittest.TestCase):
    def test_round_trip_replace_create_and_remove_intents(self):
        base = request()
        for source in (base, replace(base, current=RootRestoreFileState(False)).with_hash(),
                       replace(base, backup=RootRestoreFileState(False)).with_hash()):
            with self.subTest(source=source):
                self.assertEqual(decode(encode_request(source), source), source)

    def test_caller_and_host_must_match_independent_observation(self):
        for overrides in ({"expected_caller_uid": 1001}, {"expected_caller_uid": True},
                          {"expected_host_id": "local:other"}):
            with self.subTest(overrides=overrides), self.assertRaises(AdapterError):
                decode(encode_request(request()), **overrides)

    def test_all_review_and_target_bindings_are_hashed(self):
        base = request()
        for field in ("request_id", "host_id", "backup_id", "approval_id", "manifest_hash",
                      "inventory_hash", "preview_hash", "target"):
            value = json.loads(encode_request(base))
            value[field] = "f" * 64
            with self.subTest(field=field), self.assertRaises(AdapterError):
                decode(wire(value))
        for side in ("current", "backup"):
            value = json.loads(encode_request(base))
            value[side]["sha256"] = "f" * 64
            with self.subTest(side=side), self.assertRaises(AdapterError):
                decode(wire(value))
        with self.assertRaises(AdapterError):
            decode(encode_request(base), expected_hash="f" * 64)

    def test_rejects_expired_future_naive_and_excessive_lifetime(self):
        base = request()
        for now in (NOW - timedelta(microseconds=1), base.expires_at, NOW.replace(tzinfo=None)):
            with self.subTest(now=now), self.assertRaises(AdapterError):
                decode(encode_request(base), now=now)
        for expiry in (NOW, NOW - timedelta(seconds=1), NOW + timedelta(minutes=5, microseconds=1),
                       NOW.replace(tzinfo=None)):
            with self.subTest(expiry=expiry), self.assertRaises(AdapterError):
                encode_request(replace(base, expires_at=expiry).with_hash())

    def test_rejects_rehashed_invalid_identity_protocol_target_and_types(self):
        base = request()
        for fields in ({"protocol": "llm-manager.helper"}, {"protocol_version": True},
                       {"protocol_version": 2}, {"caller_uid": 0}, {"caller_uid": True},
                       {"caller_uid": 2**32 - 1}, {"caller_uid": -1},
                       {"request_id": "../escape"}, {"backup_id": ""},
                       {"target": "/etc/passwd"}, {"target": DROP_IN_PATH + "/../other"},
                       {"manifest_hash": "A" * 64}):
            with self.subTest(fields=fields), self.assertRaises(AdapterError):
                encode_request(replace(base, **fields).with_hash())

    def test_rejects_inconsistent_or_unsafe_file_states(self):
        base = request()
        states = (
            RootRestoreFileState(False, "a" * 64), RootRestoreFileState(True),
            replace(base.current, exists=1), replace(base.current, mode=0o666),
            replace(base.current, uid=1000), replace(base.current, gid=1000),
            replace(base.current, uid=False), replace(base.current, gid=False),
            replace(base.current, mode="644"), replace(base.current, sha256="bad"),
        )
        for side in ("current", "backup"):
            for state in states:
                with self.subTest(side=side, state=state), self.assertRaises(AdapterError):
                    encode_request(replace(base, **{side: state}).with_hash())

    def test_rejects_no_change_including_already_absent(self):
        base = request()
        for state in (base.current, RootRestoreFileState(False)):
            with self.subTest(state=state), self.assertRaises(AdapterError):
                encode_request(replace(base, current=state, backup=state).with_hash())

    def test_rejects_noncanonical_unknown_missing_duplicate_and_oversized_wire(self):
        encoded = encode_request(request())
        value = json.loads(encoded)
        unknown = {**value, "shell": "/bin/sh"}
        nested = {**value, "backup": {**value["backup"], "path": "/etc/passwd"}}
        missing = {key: item for key, item in value.items() if key != "approval_id"}
        nonfinite = {**value, "caller_uid": float("nan")}
        surrogate = {**value, "approval_id": "\ud800"}
        for content in (encoded + b'\n', wire(unknown), wire(nested), wire(missing),
                        wire(nonfinite), wire(surrogate),
                        b'{"protocol": "ignored",' + encoded[1:],
                        b'x' * (MAX_REQUEST_BYTES + 1), b'\xff', b'null', b'[]',
                        b'{"current": null}', b'[' * 2000 + b']' * 2000):
            with self.subTest(length=len(content)), self.assertRaises(AdapterError):
                decode(content)

    def test_legacy_apply_protocol_rejects_restore_and_default_availability_is_closed(self):
        base = request()
        with self.assertRaises(AdapterError):
            helper_protocol.decode_request(
                encode_request(base), expected_hash=base.request_hash, now=NOW,
            )
        availability = AssessProductionRestoreAvailability().execute(HostKind.LOCAL, True)
        self.assertFalse(availability.available)
        self.assertEqual(availability.reason_code, "local_root_restore_release_gate_pending")


if __name__ == "__main__":
    unittest.main()
