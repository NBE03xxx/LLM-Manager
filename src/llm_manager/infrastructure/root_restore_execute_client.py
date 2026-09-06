"""Unprivileged one-shot transport for the root restore execution entry."""
from __future__ import annotations

import json
import re
from datetime import datetime

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandRequest
from llm_manager.domain.models import utc_now
from llm_manager.domain.serialization import to_primitive
from .local_root_restore_protocol import encode_request, validate_request, _DIGEST
from .policykit import PKEXEC, PolicyKitRunner
from .process import ProcessPolicy, SubprocessRunner
from .root_restore_store import RootRestoreResult, RootRestoreState

EXECUTE_HELPER = '/usr/bin/llm-manager-restore-execute'
MAX_RESPONSE_BYTES = 32 * 1024


class RootRestoreExecutionUnconfirmed(AdapterError):
    """The process may have mutated the target; only status may reconcile it."""
    def __init__(self, request_id, request_hash, reported_state=None):
        super().__init__('root_restore_execution_unconfirmed',
                         'root restore execution requires read-only reconciliation')
        self.request_id = request_id
        self.request_hash = request_hash
        self.reported_state = reported_state


class RootRestoreExecuteClient:
    def __init__(self, *, caller_uid: int, host_id: str, runner: PolicyKitRunner | None = None,
                 clock=utc_now):
        self.caller_uid, self.host_id, self.clock = caller_uid, host_id, clock
        self.runner = runner if runner is not None else SubprocessRunner(
            ProcessPolicy((PKEXEC,), max_output_bytes=MAX_RESPONSE_BYTES)
        )

    def execute(self, request, cancellation: CancellationToken) -> RootRestoreResult:
        validate_request(
            request, expected_hash=request.request_hash, expected_caller_uid=self.caller_uid,
            expected_host_id=self.host_id, now=self.clock(),
        )
        content = encode_request(request)
        if cancellation.cancelled:
            raise OperationCancelled('root restore cancelled before execution')
        command = CommandRequest(
            (PKEXEC, EXECUTE_HELPER, request.request_hash, content.hex()),
            180_000, request.request_id,
        )
        try:
            process = self.runner.run(command, cancellation)
        except OperationCancelled as error:
            raise RootRestoreExecutionUnconfirmed(request.request_id, request.request_hash) from error
        except AdapterError as error:
            # The runner may have launched pkexec before an output-limit or I/O
            # failure. Do not convert this into a retryable preflight failure.
            raise RootRestoreExecutionUnconfirmed(request.request_id, request.request_hash) from error
        # Interrupted transport is not reliable evidence of a pre-execution
        # rejection, even if the captured exit code resembles a pkexec error.
        if process.timed_out or cancellation.cancelled:
            raise RootRestoreExecutionUnconfirmed(request.request_id, request.request_hash)
        if process.exit_code == 126:
            raise AdapterError('privilege_denied', 'restore authentication was denied or dismissed')
        if process.exit_code == 127:
            raise AdapterError('root_restore_launch_failed', 'PolicyKit could not launch the restore entry')
        if process.exit_code not in (0, 1):
            raise RootRestoreExecutionUnconfirmed(request.request_id, request.request_hash)
        try:
            value = _canonical_response(process.stdout)
        except AdapterError as error:
            raise RootRestoreExecutionUnconfirmed(request.request_id, request.request_hash) from error
        if process.exit_code == 1:
            try:
                state = _unconfirmed_state(value, request)
            except AdapterError as error:
                raise RootRestoreExecutionUnconfirmed(
                    request.request_id, request.request_hash
                ) from error
            raise RootRestoreExecutionUnconfirmed(request.request_id, request.request_hash, state)
        try:
            return _recorded_result(value, request)
        except (AdapterError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
            raise RootRestoreExecutionUnconfirmed(request.request_id, request.request_hash) from error


def _canonical_response(content):
    try:
        if len(content.encode('utf-8')) > MAX_RESPONSE_BYTES:
            raise ValueError('oversized')
        value = json.loads(content)
        if (not isinstance(value, dict) or
                json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n' != content):
            raise ValueError('noncanonical')
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise AdapterError('invalid_root_restore_response', 'invalid restore response') from error


def _unconfirmed_state(value, request):
    if set(value) == {'status', 'request_id', 'request_hash', 'state'} and value.get('status') == 'execution_unconfirmed':
        if (value['request_id'] != request.request_id or value['request_hash'] != request.request_hash
                or value['state'] not in {item.value for item in RootRestoreState}):
            raise AdapterError('invalid_root_restore_response', 'invalid unconfirmed restore binding')
        return RootRestoreState(value['state'])
    # Even a canonical "failed" response is not evidence that pkexec did not
    # reach mutation. Its helper-controlled reason is intentionally discarded.
    if (set(value) == {'status', 'error_code'} and value.get('status') == 'failed'
            and isinstance(value.get('error_code'), str)):
        return None
    raise AdapterError('invalid_root_restore_response', 'invalid restore failure response')


def _recorded_result(value, request):
    if (set(value) != {'status', 'request_id', 'request_hash', 'state',
                       'requires_attention', 'result'}
            or value['status'] != 'execution_recorded'
            or value['request_id'] != request.request_id
            or value['request_hash'] != request.request_hash
            or type(value['requires_attention']) is not bool
            or not isinstance(value['result'], dict)):
        raise AdapterError('invalid_root_restore_response', 'invalid recorded restore response')
    raw = value['result']
    fields = dict(raw)
    fields['state'] = RootRestoreState(fields['state'])
    fields['completed_at'] = datetime.fromisoformat(fields['completed_at'])
    record = RootRestoreResult(**fields)
    if (to_primitive(record) != raw or record.request_id != request.request_id
            or record.request_hash != request.request_hash
            or not isinstance(record.attempt_hash, str) or not _DIGEST.fullmatch(record.attempt_hash)
            or record.completed_at.tzinfo is None or record.completed_at.utcoffset() is None):
        raise AdapterError('invalid_root_restore_response', 'invalid restore result binding')
    if record.state is RootRestoreState.COMMITTED:
        if record.error_code is not None:
            raise AdapterError('invalid_root_restore_response', 'invalid committed result')
    elif not isinstance(record.error_code, str) or not re.fullmatch('[a-z][a-z0-9_]{0,63}', record.error_code):
        raise AdapterError('invalid_root_restore_response', 'invalid restore result error')
    if value['state'] != record.state.value or value['requires_attention'] is (
            record.state is RootRestoreState.COMMITTED):
        raise AdapterError('invalid_root_restore_response', 'inconsistent restore summary')
    return record
