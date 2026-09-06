import unittest
from dataclasses import replace
from datetime import timedelta

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.infrastructure.local_root_restore_preflight import (
    CheckLocalRootRestore, RootRestoreReviewEvidence,
)
from llm_manager.infrastructure.local_root_restore_protocol import RootRestoreFileState
from tests.test_local_root_restore_protocol import NOW, request


def _review(intent, approved, expires):
    return RootRestoreReviewEvidence(intent, approved, expires, "a" * 64, "b" * 64)


class Evidence:
    def __init__(self, intent=None, hook=None):
        self.intent = intent or request()
        self.review = RootRestoreReviewEvidence(self.intent, NOW, NOW + timedelta(minutes=2), "a" * 64, "b" * 64)
        self.current = self.intent.current
        self.backup = self.intent.backup
        self.unused = True
        self.calls = []
        self.hook = hook
        self.now = NOW

    def step(self, name, cancellation):
        self.calls.append(name)
        if self.hook:
            self.hook(self, name, cancellation)

    def load_review(self, request_id, cancellation):
        self.step("review", cancellation)
        return self.review

    def request_is_unused(self, request_id, cancellation):
        self.step("unused", cancellation)
        return self.unused

    def observe_target(self, target, cancellation):
        self.step("target", cancellation)
        return self.current

    def verify_backup(self, review, cancellation):
        self.step("backup", cancellation)
        return self.backup


def execute(evidence, intent=None, token=None, **overrides):
    intent = intent or evidence.intent
    args = dict(expected_hash=intent.request_hash, caller_uid=1000,
                host_id="local:host", cancellation=token or CancellationToken())
    args.update(overrides)
    return CheckLocalRootRestore(evidence, clock=lambda: evidence.now).execute(intent, **args)


class LocalRootRestorePreflightTests(unittest.TestCase):
    def test_rechecks_review_target_and_unused_request_after_backup_verification(self):
        base = request()
        for intent in (base, replace(base, current=RootRestoreFileState(False)).with_hash(),
                       replace(base, backup=RootRestoreFileState(False)).with_hash()):
            with self.subTest(intent=intent):
                evidence = Evidence(intent)
                result = execute(evidence)
                self.assertEqual(evidence.calls, ["review", "unused", "target", "backup", "review", "target", "unused"])
                self.assertEqual(result.request_hash, intent.request_hash)
                self.assertEqual(result.checked_at, NOW)
                self.assertEqual(result.expires_at, evidence.review.expires_at)

    def test_invalid_caller_binding_and_cancellation_stop_before_any_io(self):
        for overrides in ({"caller_uid": 1001}, {"host_id": "other"}, {"expected_hash": "f" * 64}):
            evidence = Evidence()
            with self.subTest(overrides=overrides), self.assertRaises(AdapterError):
                execute(evidence, **overrides)
            self.assertEqual(evidence.calls, [])
        evidence = Evidence()
        with self.assertRaises(OperationCancelled):
            execute(evidence, token=CancellationToken(cancelled=True))
        self.assertEqual(evidence.calls, [])

    def test_rehashed_forged_request_does_not_match_trusted_review(self):
        for fields in ({"backup_id": "other"}, {"manifest_hash": "f" * 64},
                       {"inventory_hash": "f" * 64}, {"preview_hash": "f" * 64},
                       {"approval_id": "other"}, {"request_id": "other"},
                       {"backup": RootRestoreFileState(False)}):
            evidence = Evidence()
            forged = replace(evidence.intent, **fields).with_hash()
            with self.subTest(fields=fields), self.assertRaises(AdapterError):
                execute(evidence, forged)
            self.assertEqual(evidence.calls, ["review"])

    def test_missing_or_invalid_trusted_review_is_rejected(self):
        for value in (None, "untrusted", RootRestoreReviewEvidence(None, NOW, NOW),
                      _review(request(), NOW + timedelta(seconds=1), NOW + timedelta(minutes=2)),
                      _review(request(), NOW, NOW),
                      _review(request(), NOW, NOW + timedelta(minutes=6)),
                      _review(request(), NOW.replace(tzinfo=None), NOW + timedelta(minutes=2))):
            evidence = Evidence()
            evidence.review = value
            with self.subTest(value=value), self.assertRaises(AdapterError):
                execute(evidence)
            self.assertEqual(evidence.calls, ["review"])

    def test_used_or_indeterminate_attempt_state_stops_before_backup(self):
        for value in (False, None, 1, "unused"):
            evidence = Evidence()
            evidence.unused = value
            with self.subTest(value=value), self.assertRaises(AdapterError):
                execute(evidence)
            self.assertEqual(evidence.calls, ["review", "unused"])

    def test_stale_or_unsafe_current_target_stops_before_backup(self):
        base = request().current
        for state in (RootRestoreFileState(False), replace(base, sha256="f" * 64),
                      replace(base, uid=1000), replace(base, mode=0o666),
                      replace(base, uid=False), replace(base, mode=420.0)):
            evidence = Evidence()
            evidence.current = state
            with self.subTest(state=state), self.assertRaises(AdapterError):
                execute(evidence)
            self.assertEqual(evidence.calls, ["review", "unused", "target"])

    def test_backup_integrity_metadata_and_absence_mismatch_are_rejected(self):
        for state in (RootRestoreFileState(False), replace(request().backup, sha256="f" * 64),
                      replace(request().backup, uid=False)):
            evidence = Evidence()
            evidence.backup = state
            with self.subTest(state=state), self.assertRaises(AdapterError):
                execute(evidence)
            self.assertEqual(evidence.calls[-1], "backup")

    def test_review_target_and_attempt_changes_during_backup_are_rejected(self):
        for change in ("review", "target", "attempt"):
            def hook(evidence, name, token):
                if name == "backup":
                    if change == "review":
                        evidence.review = replace(evidence.review, expires_at=NOW + timedelta(minutes=1))
                    elif change == "target":
                        evidence.current = replace(evidence.current, sha256="f" * 64)
                    else:
                        evidence.unused = False
            evidence = Evidence(hook=hook)
            with self.subTest(change=change), self.assertRaises(AdapterError):
                execute(evidence)

    def test_cancel_and_expiry_after_every_read_prevent_next_operation(self):
        for step in range(1, 8):
            for mode in ("cancel", "request_expiry", "review_expiry"):
                def hook(evidence, name, token):
                    if len(evidence.calls) == step:
                        if mode == "cancel":
                            token.cancel()
                        elif mode == "request_expiry":
                            evidence.now = evidence.intent.expires_at
                        else:
                            evidence.now = evidence.review.expires_at
                evidence = Evidence(hook=hook)
                expected = OperationCancelled if mode == "cancel" else AdapterError
                with self.subTest(step=step, mode=mode), self.assertRaises(expected):
                    execute(evidence)
                self.assertEqual(len(evidence.calls), step)

    def test_evidence_read_and_integrity_failures_propagate_without_more_io(self):
        for step in range(1, 8):
            def hook(evidence, name, token):
                if len(evidence.calls) == step:
                    raise AdapterError("unsafe_evidence", "unsafe evidence")
            evidence = Evidence(hook=hook)
            with self.subTest(step=step), self.assertRaises(AdapterError):
                execute(evidence)
            self.assertEqual(len(evidence.calls), step)


if __name__ == "__main__":
    unittest.main()
