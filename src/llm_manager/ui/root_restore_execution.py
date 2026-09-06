"""Final explicit-consent workflow for one exact root restore request."""
from __future__ import annotations

import os
from dataclasses import dataclass

from llm_manager.application.errors import AdapterError
from llm_manager.domain.enums import HostKind
from llm_manager.domain.models import utc_now
from llm_manager.infrastructure.local_root_restore_protocol import (
    LocalRootRestoreRequest, validate_request,
)
from llm_manager.infrastructure.root_restore_execute_client import (
    RootRestoreExecuteClient, RootRestoreExecutionUnconfirmed,
)
from llm_manager.infrastructure.root_restore_review_client import RootRestoreReviewClient
from llm_manager.infrastructure.root_restore_store import (
    RootRestoreExecutionView, RootRestoreResult, RootRestoreState,
)


@dataclass(frozen=True, slots=True)
class UnconfirmedRootRestore:
    request_id: str
    request_hash: str
    reported_state: RootRestoreState | None


@dataclass(frozen=True, slots=True)
class RejectedRootRestore:
    error_code: str


class RootRestoreExecutionSession:
    def __init__(self, execute_client, status_client, request, *, clock=utc_now):
        self.execute_client, self.status_client, self.request, self.clock = (
            execute_client, status_client, request, clock,
        )
        self.state = 'ready'
        self.result = None
        self.history = None
        self.rejection = None
        self._consent_hash = None
        self._execution_started = False
        self._status_started = False
        self._validate(self.clock())

    def _validate(self, now):
        if not isinstance(self.request, LocalRootRestoreRequest):
            raise AdapterError('invalid_root_restore_request', 'root restore request is invalid')
        validate_request(
            self.request, expected_hash=self.request.request_hash,
            expected_caller_uid=self.execute_client.caller_uid,
            expected_host_id=self.execute_client.host_id, now=now,
        )

    def expire(self):
        if self.state == 'ready':
            try:
                self._validate(self.clock())
            except AdapterError:
                self.state = 'expired'
                self._consent_hash = None

    def consent(self, checked):
        self._consent_hash = None
        self.expire()
        if checked is True:
            if self.state != 'ready':
                raise AdapterError('root_restore_state_invalid', 'restore is no longer available')
            self._consent_hash = self.request.request_hash

    @property
    def can_execute(self):
        self.expire()
        return (self.state == 'ready' and not self._execution_started
                and self._consent_hash == self.request.request_hash)

    def execute_task(self):
        if not self.can_execute:
            raise AdapterError('root_restore_consent_required', 'exact restore consent required')
        self._validate(self.clock())
        self._execution_started = True
        self._consent_hash = None
        self.state = 'executing'
        def task(token):
            try:
                return self.execute_client.execute(self.request, token)
            except RootRestoreExecutionUnconfirmed as error:
                return UnconfirmedRootRestore(
                    error.request_id, error.request_hash, error.reported_state,
                )
            except AdapterError as error:
                return RejectedRootRestore(error.code)
        return task

    def receive_execution(self, outcome):
        self._require('executing')
        if isinstance(outcome, RootRestoreResult):
            if (outcome.request_id, outcome.request_hash) != (
                    self.request.request_id, self.request.request_hash):
                self.fail()
                raise AdapterError('invalid_root_restore_response', 'restore result mismatch')
            self.result = outcome
            self.state = {
                RootRestoreState.COMMITTED: 'committed',
                RootRestoreState.FAILED: 'failed_result',
                RootRestoreState.UNKNOWN: 'unknown_result',
            }[outcome.state]
        elif isinstance(outcome, UnconfirmedRootRestore):
            if (outcome.request_id, outcome.request_hash) != (
                    self.request.request_id, self.request.request_hash):
                self.fail()
                raise AdapterError('invalid_root_restore_response', 'unconfirmed result mismatch')
            self.state = 'unconfirmed'
        elif isinstance(outcome, RejectedRootRestore):
            if not isinstance(outcome.error_code, str) or not outcome.error_code:
                self.fail()
                raise AdapterError('invalid_root_restore_response', 'invalid rejection')
            self.rejection = outcome.error_code
            self.state = 'rejected'
        else:
            self.fail()
            raise AdapterError('invalid_root_restore_response', 'unknown restore result')

    @property
    def can_check_status(self):
        return self.state == 'unconfirmed' and not self._status_started

    def status_task(self):
        if not self.can_check_status:
            raise AdapterError('root_restore_state_invalid', 'restore status is unavailable')
        self._status_started = True
        self.state = 'checking'
        return lambda token: self.status_client.status(self.request, token)

    def receive_status(self, history):
        self._require('checking')
        if not isinstance(history, RootRestoreExecutionView) or (
                history.result is not None and history.attempt is None) or any(
            (item.request_id, item.request_hash) != (self.request.request_id, self.request.request_hash)
            for item in (history.attempt, history.result) if item is not None
        ):
            self.fail('status_failed')
            raise AdapterError('invalid_root_restore_response', 'restore history mismatch')
        self.history = history
        self.state = 'checked'

    def worker_failed(self, phase):
        self._consent_hash = None
        if phase == 'executing':
            self.state = 'unconfirmed'
        elif phase == 'checking':
            self.state = 'status_failed'
        else:
            self.state = 'failed'

    def fail(self, state='failed'):
        self.state = state
        self._consent_hash = None
        self.result = None
        self.history = None
        self.rejection = None

    def _require(self, state):
        if self.state != state:
            raise AdapterError('root_restore_state_invalid', 'restore workflow is no longer available')


def production_execution_session(host, request):
    host_id = 'local:' + os.uname().nodename
    if host.kind != HostKind.LOCAL or host.host_id != host_id or os.getuid() == 0:
        raise AdapterError('root_restore_requires_local_user', 'local user restore required')
    execute = RootRestoreExecuteClient(caller_uid=os.getuid(), host_id=host_id)
    status = RootRestoreReviewClient(caller_uid=os.getuid(), host_id=host_id)
    return RootRestoreExecutionSession(execute, status, request)


def create_production_execution_dialog(host, request, *, locale='en', parent=None):
    """Explicit composition only; not registered in the production menu."""
    from .qt_root_restore_execution import RootRestoreExecutionDialog
    return RootRestoreExecutionDialog(
        production_execution_session(host, request), locale=locale, parent=parent,
    )
