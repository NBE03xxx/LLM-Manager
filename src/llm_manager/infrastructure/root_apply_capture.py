"""Origin capture for the authenticated local Apply entry, inside its target lock."""
import os
from contextlib import ExitStack

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import utc_now
from .backup_crypto import AesGcmBackupCipher
from .helper_protocol import HelperOperationKind as Kind, validate_request
from .local_root_key_provisioning import open_production_key_directory
from .root_backup_capture import CaptureRootBackup, LocalRootBackupKeys
from .root_backup_evidence import open_production_directory

PRODUCTION_KEY_ID = 'local-root-v1'


def validate_capture_request(request, *, host_id):
    validate_request(request, request.request_hash, now=utc_now())
    kinds = tuple(item.kind for item in request.operations)
    if (request.host_id != host_id or request.backup_id is None
            or request.approval_id is None or request.manifest_hash is None
            or kinds not in ((Kind.ATOMIC_REPLACE,),
                             (Kind.ATOMIC_REPLACE, Kind.DAEMON_RELOAD),
                             (Kind.ATOMIC_REPLACE, Kind.DAEMON_RELOAD, Kind.RESTART_UNIT))):
        raise AdapterError('invalid_root_capture_apply', 'root capture requires a bound local Apply')


def capture_before_replace(request, target_fd):
    """Borrow the helper's already-locked FD. Never reopen or unlock the target.

    Called only after the privileged entry authenticates the user, claims the
    receipt, and the executor verifies both the current hash and staged bytes.
    This function does not authenticate, initialize state, or reserve a request.
    """
    if os.geteuid() != 0:
        raise AdapterError('root_required', 'root capture requires root')
    validate_capture_request(request, host_id='local:' + os.uname().nodename)
    with ExitStack() as stack:
        def owned(opener):
            fd = opener()
            stack.callback(os.close, fd)
            return fd
        keys = LocalRootBackupKeys(owned(open_production_key_directory))
        # Require explicit setup even for an absent original (no ciphertext).
        keys.get_key(PRODUCTION_KEY_ID, 'local_root')
        capture = CaptureRootBackup(owned(open_production_directory), target_fd,
                                    AesGcmBackupCipher(keys))
        capture.execute(request, expected_hash=request.request_hash,
                        key_id=PRODUCTION_KEY_ID, cancellation=CancellationToken())
