"""Dedicated privileged root restore execution entry.

This executable must have its own PolicyKit action. Review authentication and
the ordinary Apply action are never execution authority. An interrupted or
unconfirmed call must be reconciled through the read-only status command; it
must not be retried automatically.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import utc_now
from llm_manager.domain.serialization import to_primitive
from .local_root_restore_protocol import MAX_REQUEST_BYTES, decode_request
from .root_backup_evidence import _HASH
from .root_restore_composition import production_execution
from .root_restore_execution import RootRestorePersistenceError
from .root_restore_review import resolve_restore_caller
from .root_restore_store import RootRestoreResult, RootRestoreState


def main(argv=None):
    parser = argparse.ArgumentParser(prog='llm-manager-restore-execute', allow_abbrev=False)
    parser.add_argument('expected_hash')
    parser.add_argument('request_hex')
    args = parser.parse_args(argv)
    request = None
    try:
        caller = resolve_restore_caller()
        content = _request_content(args.expected_hash, args.request_hex)
        request = decode_request(
            content, expected_hash=args.expected_hash, expected_caller_uid=caller.uid,
            expected_host_id=caller.host_id, now=utc_now(),
        )
        with production_execution() as executor:
            result_record = executor.execute(
                request, expected_hash=args.expected_hash, caller_uid=caller.uid,
                host_id=caller.host_id, cancellation=CancellationToken(),
            )
        result = _result_response(request, result_record)
        exit_code = 0
    except RootRestorePersistenceError as error:
        # Mutation may have occurred. Provide only stable binding metadata and
        # require a separate read-only reconciliation; never report "failed".
        result = {
            'status': 'execution_unconfirmed',
            'request_id': request.request_id if request is not None else None,
            'request_hash': error.request_hash,
            'state': error.state.value,
        }
        exit_code = 1
    except OperationCancelled:
        result = {'status': 'failed', 'error_code': 'root_restore_cancelled'}
        exit_code = 1
    except AdapterError as error:
        result = {'status': 'failed', 'error_code': error.code}
        exit_code = 1
    except Exception:
        # No exception text, traceback, decrypted settings, paths or service
        # output on stdout. The exact outcome may require status reconciliation.
        result = {'status': 'failed', 'error_code': 'root_restore_unavailable'}
        exit_code = 1
    sys.stdout.write(json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n')
    return exit_code


def _request_content(expected_hash, request_hex):
    if (not isinstance(expected_hash, str) or not _HASH.fullmatch(expected_hash)
            or not isinstance(request_hex, str) or not request_hex
            or len(request_hex) > MAX_REQUEST_BYTES * 2 or len(request_hex) % 2):
        raise AdapterError('invalid_restore_argument', 'invalid restore request encoding')
    try:
        content = bytes.fromhex(request_hex)
    except ValueError:
        raise AdapterError('invalid_restore_argument', 'invalid restore request encoding') from None
    if content.hex() != request_hex:
        raise AdapterError('invalid_restore_argument', 'noncanonical restore request encoding')
    return content


def _result_response(request, record):
    if (not isinstance(record, RootRestoreResult)
            or record.request_id != request.request_id
            or record.request_hash != request.request_hash
            or not isinstance(record.attempt_hash, str) or not _HASH.fullmatch(record.attempt_hash)
            or not isinstance(record.state, RootRestoreState)
            or record.completed_at.tzinfo is None or record.completed_at.utcoffset() is None):
        raise AdapterError('invalid_root_restore_result', 'invalid root restore result binding')
    if record.state is RootRestoreState.COMMITTED:
        if record.error_code is not None:
            raise AdapterError('invalid_root_restore_result', 'invalid committed restore result')
    elif not isinstance(record.error_code, str) or not re.fullmatch('[a-z][a-z0-9_]{0,63}', record.error_code):
        raise AdapterError('invalid_root_restore_result', 'invalid root restore error code')
    return {
        'status': 'execution_recorded',
        'request_id': request.request_id,
        'request_hash': request.request_hash,
        'state': record.state.value,
        'requires_attention': record.state is not RootRestoreState.COMMITTED,
        'result': to_primitive(record),
    }


if __name__ == '__main__':
    raise SystemExit(main())
