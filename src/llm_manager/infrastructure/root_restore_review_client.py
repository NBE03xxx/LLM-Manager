"""Unprivileged, one-shot transport for dedicated root restore review.

A saved review is neither consent collection nor permission to execute restore.
No automatic retry: an interrupted approve may already have saved the review.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandRequest
from llm_manager.domain.models import utc_now
from llm_manager.domain.serialization import to_primitive
from .local_root_restore_protocol import (
    RootRestoreFileState, encode_request, validate_request, _validate_file_state,
    _DIGEST, _IDENTIFIER,
)
from .policykit import PKEXEC, PolicyKitRunner
from .process import ProcessPolicy, SubprocessRunner
from .root_restore_review import RootRestoreSelection
from .root_restore_store import (
    RootRestoreAttempt, RootRestoreResult, RootRestoreExecutionView, RootRestoreState, _validate_result,
)
from .root_backup_evidence import RootBackupInventoryItem

REVIEW_HELPER = '/usr/bin/llm-manager-restore-review'
MAX_RESPONSE_BYTES = 32 * 1024


def _reject(code='invalid_restore_review_response'):
    raise AdapterError(code, 'root restore review could not be confirmed')


@dataclass(frozen=True, slots=True)
class SavedRootRestoreReview:
    request_id: str
    request_hash: str


class RootRestoreReviewClient:
    def __init__(self, *, caller_uid: int, host_id: str, runner: PolicyKitRunner | None = None,
                 clock=utc_now):
        self.caller_uid, self.host_id, self.clock = caller_uid, host_id, clock
        self.runner = runner if runner is not None else SubprocessRunner(
            ProcessPolicy((PKEXEC,), max_output_bytes=MAX_RESPONSE_BYTES))

    def list_backups(self, cancellation: CancellationToken) -> tuple[RootBackupInventoryItem, ...]:
        value = self._invoke(('list',), 'root-backup-inventory', cancellation)
        try:
            if (set(value) != {'status', 'host_id', 'items'}
                    or value['status'] != 'root_backup_inventory'
                    or value['host_id'] != self.host_id
                    or not isinstance(value['items'], list)
                    or len(value['items']) > 32):
                _reject()
            items = []
            for raw in value['items']:
                fields = dict(raw)
                fields['captured_at'] = datetime.fromisoformat(fields['captured_at'])
                fields['original'] = RootRestoreFileState(**fields['original'])
                item = RootBackupInventoryItem(**fields)
                if (to_primitive(item) != raw or item.host_id != self.host_id
                        or not _IDENTIFIER.fullmatch(item.backup_id)
                        or item.captured_at.tzinfo is None
                        or item.captured_at.utcoffset() is None
                        or any(not _DIGEST.fullmatch(digest) for digest in (
                            item.record_hash, item.source_apply_request_hash,
                            item.source_manifest_hash))):
                    _reject()
                _validate_file_state(item.original)
                items.append(item)
            if tuple(item.backup_id for item in items) != tuple(sorted(
                    item.backup_id for item in items)) or len({item.backup_id for item in items}) != len(items):
                _reject()
            return tuple(items)
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError, AdapterError):
            _reject()

    def preview(self, backup_id: str, cancellation: CancellationToken) -> RootRestoreSelection:
        if not isinstance(backup_id, str) or not _IDENTIFIER.fullmatch(backup_id):
            _reject('invalid_restore_argument')
        value = self._invoke(('preview', backup_id), backup_id, cancellation)
        try:
            if set(value) != {'status', 'selection', 'preview_hash'} or value['status'] != 'preview':
                _reject()
            raw = value['selection']
            fields = dict(raw)
            fields['current'] = RootRestoreFileState(**fields['current'])
            fields['backup'] = RootRestoreFileState(**fields['backup'])
            fields['created_at'] = datetime.fromisoformat(fields['created_at'])
            fields['expires_at'] = datetime.fromisoformat(fields['expires_at'])
            selection = RootRestoreSelection(**fields)
            if to_primitive(selection) != raw or selection.backup_id != backup_id:
                _reject()
            self.validate_selection(selection)
            if value['preview_hash'] != selection.preview_hash:
                _reject()
            return selection
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
            _reject()

    def approve(self, selection: RootRestoreSelection, *, request_id: str, approval_id: str,
                cancellation: CancellationToken) -> SavedRootRestoreReview:
        # Caller must first display this exact selection and collect explicit consent.
        self.validate_selection(selection)
        request = selection.request(request_id, approval_id)
        content = encode_request(request)
        value = self._invoke(('approve', request.request_hash, content.hex()), request_id, cancellation)
        if value != {'status': 'review_saved', 'request_id': request_id, 'request_hash': request.request_hash}:
            _reject()
        return SavedRootRestoreReview(request_id, request.request_hash)

    def validate_selection(self, selection):
        for digest in (selection.origin_record_hash, selection.source_apply_request_hash):
            if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
                _reject()
        request = selection.request('preview-validation', 'preview-validation')
        validate_request(request, expected_hash=request.request_hash,
                         expected_caller_uid=self.caller_uid, expected_host_id=self.host_id, now=self.clock())

    def status(self, request, cancellation: CancellationToken) -> RootRestoreExecutionView:
        """Reconcile an exact historical intent; never authorize or retry it."""
        validate_request(request, expected_hash=request.request_hash,
                         expected_caller_uid=self.caller_uid, expected_host_id=self.host_id,
                         now=request.requested_at)
        value = self._invoke(('status', request.request_id, request.request_hash),
                             request.request_id, cancellation)
        try:
            if (set(value) != {'status', 'request_id', 'request_hash', 'state',
                               'requires_attention', 'attempt', 'result'}
                    or value['status'] != 'execution_status'
                    or value['request_id'] != request.request_id
                    or value['request_hash'] != request.request_hash
                    or type(value['requires_attention']) is not bool):
                _reject()
            attempt = result = None
            if value['attempt'] is not None:
                fields = dict(value['attempt'])
                fields['started_at'] = datetime.fromisoformat(fields['started_at'])
                attempt = RootRestoreAttempt(**fields)
                if (to_primitive(attempt) != value['attempt']
                        or attempt.request_id != request.request_id
                        or attempt.request_hash != request.request_hash
                        or not isinstance(attempt.review_hash, str)
                        or not _DIGEST.fullmatch(attempt.review_hash)
                        or not request.requested_at <= attempt.started_at < request.expires_at):
                    _reject()
            if value['result'] is not None:
                if attempt is None:
                    _reject()
                fields = dict(value['result'])
                fields['completed_at'] = datetime.fromisoformat(fields['completed_at'])
                fields['state'] = RootRestoreState(fields['state'])
                result = RootRestoreResult(**fields)
                _validate_result(result, attempt)
                if to_primitive(result) != value['result']:
                    _reject()
            view = RootRestoreExecutionView(attempt, result)
            state = result.state.value if result is not None else 'unknown' if attempt is not None else 'review_only'
            if value['state'] != state or value['requires_attention'] is not view.requires_attention:
                _reject()
            return view
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError, AdapterError):
            _reject()

    def _invoke(self, args, correlation_id, cancellation):
        if cancellation.cancelled:
            raise OperationCancelled('restore review cancelled')
        result = self.runner.run(CommandRequest((PKEXEC, REVIEW_HELPER, *args), 120_000, correlation_id), cancellation)
        if cancellation.cancelled:
            raise OperationCancelled('restore review cancelled')
        if result.timed_out:
            _reject('restore_review_timeout')
        if result.exit_code == 126:
            _reject('privilege_denied')
        if result.exit_code == 127:
            _reject('restore_review_launch_failed')
        if result.exit_code not in (0, 1):
            _reject('restore_review_unavailable')
        try:
            if len(result.stdout.encode('utf-8')) > MAX_RESPONSE_BYTES:
                _reject()
            value = json.loads(result.stdout)
            if not isinstance(value, dict):
                _reject()
            if json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n' != result.stdout:
                _reject()
        except (ValueError, TypeError, UnicodeError, RecursionError):
            _reject()
        if result.exit_code == 1:
            # Never display helper-controlled strings (including error_code/stderr).
            if set(value) != {'status', 'error_code'} or value['status'] != 'failed' or not isinstance(value['error_code'], str):
                _reject()
            _reject('restore_review_rejected')
        return value
