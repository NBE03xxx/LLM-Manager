"""Dedicated privileged review entry; never dispatches a restore mutation."""
from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import ExitStack, contextmanager

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.serialization import to_primitive
from .backup_crypto import AesGcmBackupCipher
from .local_root_key_provisioning import open_production_key_directory
from .local_root_restore_protocol import MAX_REQUEST_BYTES
from .root_backup_capture import LocalRootBackupKeys
from .root_backup_evidence import RootBackupEvidenceReader, open_production_directory, _ID, _HASH
from .root_restore_execution import SingleRootRestoreTarget, open_production_source_parent
from .root_restore_review import ProduceRootRestoreReview, resolve_restore_caller
from .root_restore_store import RootRestoreStore, open_production_execution_directory


@contextmanager
def production_review(caller):
    # No request-controlled paths, owner overrides, directory creation or keys.
    with ExitStack() as stack:
        def owned_fd(opener):
            fd = opener()
            stack.callback(os.close, fd)
            return fd
        origins = RootBackupEvidenceReader(owned_fd(open_production_directory))
        cipher = AesGcmBackupCipher(LocalRootBackupKeys(owned_fd(open_production_key_directory)))
        target = SingleRootRestoreTarget(owned_fd(open_production_source_parent))
        store = RootRestoreStore(owned_fd(open_production_execution_directory))
        yield ProduceRootRestoreReview(origins, cipher, target, store, identity=lambda: caller)


@contextmanager
def production_status():
    # History does not require available keys, backup payload or live target.
    fd = open_production_execution_directory()
    try:
        yield RootRestoreStore(fd)
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='llm-manager-restore-review', allow_abbrev=False)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list', allow_abbrev=False)
    preview = commands.add_parser('preview', allow_abbrev=False)
    preview.add_argument('backup_id')
    approve = commands.add_parser('approve', allow_abbrev=False)
    approve.add_argument('expected_hash')
    approve.add_argument('request_hex')
    status = commands.add_parser('status', allow_abbrev=False)
    status.add_argument('request_id')
    status.add_argument('expected_hash')
    args = parser.parse_args(argv)
    try:
        caller = resolve_restore_caller()
        content = None
        if args.command == 'list':
            pass
        elif args.command == 'preview':
            if not _ID.fullmatch(args.backup_id):
                raise AdapterError('invalid_restore_argument', 'invalid backup ID')
        elif args.command == 'status':
            if not _ID.fullmatch(args.request_id) or not _HASH.fullmatch(args.expected_hash):
                raise AdapterError('invalid_restore_argument', 'invalid status binding')
        else:
            # Bounded argv transport contains metadata only. No stdin wait or
            # user-owned pathname traversal in a privileged process.
            if (not _HASH.fullmatch(args.expected_hash) or not args.request_hex
                    or len(args.request_hex) > MAX_REQUEST_BYTES * 2
                    or len(args.request_hex) % 2):
                raise AdapterError('invalid_restore_argument', 'invalid request encoding')
            try:
                content = bytes.fromhex(args.request_hex)
            except ValueError:
                raise AdapterError('invalid_restore_argument', 'invalid request encoding') from None
            if content.hex() != args.request_hex:
                raise AdapterError('invalid_restore_argument', 'noncanonical request encoding')
        if args.command == 'list':
            fd = open_production_directory()
            try:
                items = tuple(item for item in RootBackupEvidenceReader(fd).list_inventory(
                    CancellationToken()) if item.host_id == caller.host_id)
            finally:
                os.close(fd)
            result = {'status': 'root_backup_inventory', 'host_id': caller.host_id,
                      'items': to_primitive(items)}
        elif args.command == 'status':
            with production_status() as store:
                view = store.reconcile(args.request_id, expected_hash=args.expected_hash,
                                       caller_uid=caller.uid, host_id=caller.host_id,
                                       cancellation=CancellationToken())
            state = (view.result.state.value if view.result is not None else
                     'unknown' if view.attempt is not None else 'review_only')
            result = {'status': 'execution_status', 'request_id': args.request_id,
                      'request_hash': args.expected_hash, 'state': state,
                      'requires_attention': view.requires_attention,
                      'attempt': to_primitive(view.attempt), 'result': to_primitive(view.result)}
        else:
            result = _review_result(args, content, caller)
    except OperationCancelled:
        result = {'status': 'failed', 'error_code': 'restore_review_cancelled'}
    except AdapterError as error:
        result = {'status': 'failed', 'error_code': error.code}
    except Exception:
        # No traceback, exception text, configuration or key material on stdout.
        result = {'status': 'failed', 'error_code': 'restore_review_unavailable'}
    sys.stdout.write(json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n')
    return 1 if result['status'] == 'failed' else 0


def _review_result(args, content, caller):
    with production_review(caller) as producer:
        token = CancellationToken()
        if args.command == 'preview':
            selection = producer.preview(args.backup_id, token)
            result = {'status': 'preview', 'selection': to_primitive(selection), 'preview_hash': selection.preview_hash}
        else:
            review = producer.approve(content, args.expected_hash, token)
            result = {'status': 'review_saved', 'request_id': review.approved_request.request_id,
                      'request_hash': review.approved_request.request_hash}
    return result


if __name__ == '__main__':
    raise SystemExit(main())
