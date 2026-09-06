"""Fixed privileged restore assembly; no CLI or authorization dispatch.

Only a future dedicated execution action may use this assembly. Root identity
and a stored review alone do not replace that action's authentication gate.
"""
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import os

from llm_manager.application.errors import AdapterError
from .backup_crypto import AesGcmBackupCipher
from .local_root_key_provisioning import open_production_key_directory
from .local_root_restore_preflight import CheckLocalRootRestore
from .root_backup_capture import LocalRootBackupKeys
from .root_backup_evidence import RootBackupEvidenceReader, open_production_directory
from .root_backup_verification import VerifyRootBackupOrigin
from .root_restore_audit import RootRestoreAuditLog, open_production_audit_directory
from .root_restore_execution import ExecuteLocalRootRestore, SingleRootRestoreTarget, open_production_source_parent
from .root_restore_service import RootRestoreOllamaService
from .root_restore_store import RootRestoreStore, open_production_execution_directory


@dataclass(frozen=True)
class StoredRootRestorePreflight:
    store: RootRestoreStore
    target: SingleRootRestoreTarget
    verifier: VerifyRootBackupOrigin

    def load_review(self, request_id, cancellation):
        return self.store.load_review(request_id, cancellation)

    def request_is_unused(self, request_id, cancellation):
        return self.store.request_is_unused(request_id, cancellation)

    def observe_target(self, target, cancellation):
        return self.target.observe_target(target, cancellation)

    def verify_backup(self, evidence, cancellation):
        return self.verifier.execute(evidence, cancellation)


@contextmanager
def production_execution():
    """Borrow components only inside this context; all FDs close on exit.

    No path/owner/runner overrides, provisioning, or execution at construction.
    No caller-controlled identity is inferred here. The dedicated dispatcher
    must independently resolve identity and authenticate before using it.
    """
    if os.geteuid() != 0:
        raise AdapterError('root_required', 'root restore assembly requires root')
    with ExitStack() as stack:
        def owned(opener):
            fd = opener()
            stack.callback(os.close, fd)
            return fd
        origins = RootBackupEvidenceReader(owned(open_production_directory))
        keys = LocalRootBackupKeys(owned(open_production_key_directory))
        cipher = AesGcmBackupCipher(keys)
        target = SingleRootRestoreTarget(owned(open_production_source_parent))
        store = RootRestoreStore(owned(open_production_execution_directory))
        audit = RootRestoreAuditLog(owned(open_production_audit_directory))
        # Reject an unsafe/incomplete chain before exposing the coordinator.
        audit.read_all()
        verifier = VerifyRootBackupOrigin(origins, cipher)
        evidence = StoredRootRestorePreflight(store, target, verifier)
        yield ExecuteLocalRootRestore(store, CheckLocalRootRestore(evidence), origins,
                                      verifier, target, audit, RootRestoreOllamaService())
