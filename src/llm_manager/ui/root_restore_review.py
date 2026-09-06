"""Consent workflow for review only; no restore executor or mutation authority."""
from __future__ import annotations

import os
import uuid

from llm_manager.application.errors import AdapterError
from llm_manager.domain.enums import HostKind
from llm_manager.domain.models import utc_now
from llm_manager.infrastructure.local_root_restore_protocol import validate_request
from llm_manager.infrastructure.root_restore_review import RootRestoreSelection
from llm_manager.infrastructure.root_restore_review_client import RootRestoreReviewClient, SavedRootRestoreReview
from llm_manager.infrastructure.root_restore_store import RootRestoreExecutionView


class RootRestoreReviewSession:
    def __init__(self, client, backup_id, *, clock=utc_now):
        self.client, self.backup_id, self.clock = client, backup_id, clock
        self.state = 'new'
        self.selection = None
        self.receipt = None
        self._consent_hash = None
        self._request = None
        self.history = None
        self._status_started = False

    @property
    def can_check_status(self):
        return self._request is not None and self.state in ('saved', 'failed') and not self._status_started

    def status_task(self):
        if not self.can_check_status:
            raise AdapterError('restore_review_state_invalid', 'history is not available')
        self._status_started = True
        self.state = 'checking'
        request = self._request
        return lambda token: self.client.status(request, token)

    def receive_status(self, history):
        self._require('checking')
        if not isinstance(history, RootRestoreExecutionView) or (
            history.result is not None and history.attempt is None
        ) or any((item.request_id, item.request_hash) != (self._request.request_id, self._request.request_hash)
                 for item in (history.attempt, history.result) if item is not None):
            self.fail()
            raise AdapterError('invalid_restore_review_response', 'history binding mismatch')
        # Full wire validation belongs to the dedicated client; this boundary
        # also rejects a delayed result from another request or closed dialog.
        self.history = history
        self.state = 'checked'

    def preview_task(self):
        self._require('new')
        self.state = 'loading'
        return lambda token: self.client.preview(self.backup_id, token)

    def receive_preview(self, selection):
        self._require('loading')
        if not isinstance(selection, RootRestoreSelection) or selection.backup_id != self.backup_id:
            self.fail()
            raise AdapterError('invalid_restore_review_response', 'review selection mismatch')
        self.client.validate_selection(selection)
        self.selection = selection
        self.state = 'ready'
        self.expire()

    def consent(self, checked):
        self._consent_hash = None
        self.expire()
        if checked is True:
            self._require('ready')
            self._consent_hash = self.selection.preview_hash

    @property
    def can_save(self):
        self.expire()
        return (self.state == 'ready' and self.selection is not None
                and self._consent_hash == self.selection.preview_hash)

    def save_task(self):
        if not self.can_save:
            raise AdapterError('restore_review_consent_required', 'exact review consent required')
        selection = self.selection
        self.client.validate_selection(selection)
        request_id, approval_id = 'review-' + uuid.uuid4().hex, 'consent-' + uuid.uuid4().hex
        self._request = selection.request(request_id, approval_id)
        self.state = 'saving'
        self._consent_hash = None
        return lambda token: self.client.approve(selection, request_id=request_id,
                                                approval_id=approval_id, cancellation=token)

    def receive_receipt(self, receipt):
        self._require('saving')
        if not isinstance(receipt, SavedRootRestoreReview) or (
            receipt.request_id, receipt.request_hash
        ) != (self._request.request_id, self._request.request_hash):
            self.fail()
            raise AdapterError('invalid_restore_review_response', 'review receipt mismatch')
        self.receipt = receipt
        self.selection = None
        self.state = 'saved'

    def approved_request_for_execution(self):
        """Return only the exact, still-live request covered by the saved receipt."""
        self._require('saved')
        if self._request is None or self.receipt is None or (
            self.receipt.request_id, self.receipt.request_hash
        ) != (self._request.request_id, self._request.request_hash):
            raise AdapterError('invalid_restore_review_response', 'saved review binding mismatch')
        validate_request(
            self._request, expected_hash=self.receipt.request_hash,
            expected_caller_uid=self.client.caller_uid,
            expected_host_id=self.client.host_id, now=self.clock(),
        )
        return self._request

    def expire(self):
        if self.state == 'ready' and not self.selection.created_at <= self.clock() < self.selection.expires_at:
            self.fail('expired')

    def fail(self, state='failed'):
        self.state = state
        self.selection = None
        self._consent_hash = None
        self.receipt = None
        self.history = None

    def _require(self, state):
        if self.state != state:
            raise AdapterError('restore_review_state_invalid', 'review workflow is no longer available')


def production_review_session(host, backup_id):
    """Construct without I/O; GUI entry remains gated pending installed OS tests."""
    host_id = 'local:' + os.uname().nodename
    if host.kind != HostKind.LOCAL or host.host_id != host_id or os.getuid() == 0:
        raise AdapterError('root_review_requires_local_user', 'local user review required')
    return RootRestoreReviewSession(RootRestoreReviewClient(caller_uid=os.getuid(), host_id=host_id), backup_id)


def create_production_review_dialog(host, backup_id, *, locale='en', parent=None):
    """Explicit review-only composition; not registered in the production menu yet."""
    from .qt_root_restore_review import RootRestoreReviewDialog
    return RootRestoreReviewDialog(production_review_session(host, backup_id), locale=locale, parent=parent)
