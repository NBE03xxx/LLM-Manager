"""Read-only local root restore preflight; production adapters are not wired.

Trusted evidence must originate in privileged backup/review processing, never
from merely rehashing user-supplied manifests. The result is a check outcome,
not a transferable authorization or a reservation of the request ID.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import utc_now

from .local_root_restore_protocol import (
    LocalRootRestoreRequest, RootRestoreFileState, validate_request,
)


@dataclass(frozen=True, slots=True)
class RootRestoreReviewEvidence:
    approved_request: LocalRootRestoreRequest
    approved_at: datetime
    expires_at: datetime
    origin_record_hash: str | None = None
    source_apply_request_hash: str | None = None


class RootRestorePreflightPort(Protocol):
    """Future privileged adapter, with strict records and no write operations.

    All methods must reject missing/corrupt/unsafe evidence. Target observation
    includes regular-file and no-symlink checks through every parent. Backup
    verification checks trusted origin, decryption/integrity and metadata.
    request_is_unused returns False for ANY attempt/result, including unknown;
    malformed stores must raise, not report an unused request.
    """

    def load_review(self, request_id: str, cancellation: CancellationToken) -> RootRestoreReviewEvidence: ...

    def request_is_unused(self, request_id: str, cancellation: CancellationToken) -> bool: ...

    def observe_target(self, target: str, cancellation: CancellationToken) -> RootRestoreFileState: ...

    def verify_backup(self, evidence: RootRestoreReviewEvidence, cancellation: CancellationToken) -> RootRestoreFileState: ...


@dataclass(frozen=True, slots=True)
class CheckedRootRestoreIntent:
    request_hash: str
    checked_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class CheckLocalRootRestore:
    evidence: RootRestorePreflightPort
    clock: Callable[[], datetime] = utc_now

    def execute(
        self, request: LocalRootRestoreRequest, *, expected_hash: str,
        caller_uid: int, host_id: str, cancellation: CancellationToken,
    ) -> CheckedRootRestoreIntent:
        def checkpoint(review: RootRestoreReviewEvidence | None = None) -> datetime:
            if cancellation.cancelled:
                raise OperationCancelled("local root restore preflight cancelled")
            now = self.clock()
            validate_request(
                request, expected_hash=expected_hash, expected_caller_uid=caller_uid,
                expected_host_id=host_id, now=now,
            )
            if review is not None:
                _validate_review(review, request, now)
            return now

        checkpoint()
        review = self.evidence.load_review(request.request_id, cancellation)
        _validate_review(review, request, checkpoint())
        unused = self.evidence.request_is_unused(request.request_id, cancellation)
        checkpoint(review)
        if unused is not True:
            _reject("root_restore_request_already_used")
        observed = self.evidence.observe_target(request.target, cancellation)
        checkpoint(review)
        if not _same_state(observed, request.current):
            _reject("root_restore_target_changed")
        backup = self.evidence.verify_backup(review, cancellation)
        checkpoint(review)
        if not _same_state(backup, request.backup):
            _reject("root_restore_backup_changed")
        refreshed = self.evidence.load_review(request.request_id, cancellation)
        _validate_review(refreshed, request, checkpoint())
        if refreshed != review:
            _reject("root_restore_review_changed")
        observed = self.evidence.observe_target(request.target, cancellation)
        checkpoint(review)
        if not _same_state(observed, request.current):
            _reject("root_restore_target_changed")
        unused = self.evidence.request_is_unused(request.request_id, cancellation)
        now = checkpoint(review)
        if unused is not True:
            _reject("root_restore_request_already_used")
        return CheckedRootRestoreIntent(request.request_hash, now, review.expires_at)


def _validate_review(
    review: RootRestoreReviewEvidence, request: LocalRootRestoreRequest, now: datetime,
) -> None:
    if not isinstance(review, RootRestoreReviewEvidence):
        _reject("invalid_root_restore_review")
    for digest in (review.origin_record_hash, review.source_apply_request_hash):
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            _reject("invalid_root_restore_origin_binding")
    # Encode equality must not accept bools as integer metadata in trusted input.
    if not isinstance(review.approved_request, LocalRootRestoreRequest):
        _reject("invalid_root_restore_review")
    validate_request(
        review.approved_request, expected_hash=request.request_hash,
        expected_caller_uid=request.caller_uid, expected_host_id=request.host_id, now=now,
    )
    if review.approved_request != request:
        _reject("root_restore_review_mismatch")
    for value in (review.approved_at, review.expires_at):
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            _reject("invalid_root_restore_review")
    if not (
        request.requested_at <= review.approved_at <= now < review.expires_at <= request.expires_at
    ):
        _reject("expired_root_restore_review")


def _same_state(observed: RootRestoreFileState, expected: RootRestoreFileState) -> bool:
    # The expected state is protocol-validated. Require exact scalar types as
    # dataclass equality alone would accept False == 0 or 420.0 == 420.
    return isinstance(observed, RootRestoreFileState) and all(
        type(getattr(observed, field)) is type(getattr(expected, field))
        and getattr(observed, field) == getattr(expected, field)
        for field in ("exists", "sha256", "mode", "uid", "gid")
    )


def _reject(code: str) -> None:
    raise AdapterError(code, "local root restore preflight rejected")
