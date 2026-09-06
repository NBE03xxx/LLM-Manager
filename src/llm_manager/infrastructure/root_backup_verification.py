"""Origin/AEAD verification component for the privileged preflight port."""
from __future__ import annotations

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from .backup_crypto import AesGcmBackupCipher
from .local_root_restore_preflight import RootRestoreReviewEvidence, _same_state
from .local_root_restore_protocol import LocalRootRestoreRequest, RootRestoreFileState, encode_request
from .root_backup_capture import decrypt_root_backup
from .root_backup_evidence import RootBackupEvidenceReader, _cancel, _HASH


class VerifyRootBackupOrigin:
    def __init__(self, reader: RootBackupEvidenceReader, cipher: AesGcmBackupCipher):
        self.reader, self.cipher = reader, cipher

    def execute(self, review: RootRestoreReviewEvidence, cancellation: CancellationToken) -> RootRestoreFileState:
        _cancel(cancellation)
        # The caller must load review from its trusted store. This component
        # does not assert review authenticity or issue mutation authority.
        if not isinstance(review, RootRestoreReviewEvidence):
            _reject()
        for value in (review.origin_record_hash, review.source_apply_request_hash):
            if not isinstance(value, str) or not _HASH.fullmatch(value):
                _reject()
        intent = review.approved_request
        if not isinstance(intent, LocalRootRestoreRequest):
            _reject()
        encode_request(intent)
        record, envelope = self.reader.read(intent.backup_id, review.origin_record_hash, cancellation)
        if (
            record.host_id != intent.host_id or record.target != intent.target
            or record.source_manifest_hash != intent.manifest_hash
            or record.source_apply_request_hash != review.source_apply_request_hash
            or not _same_state(record.original, intent.backup)
        ):
            _reject()
        if record.original.exists:
            decrypt_root_backup(record, envelope, self.cipher)
        elif envelope is not None:
            _reject()
        _cancel(cancellation)
        # Catch record/payload replacement during key access or decryption.
        if self.reader.read(intent.backup_id, review.origin_record_hash, cancellation) != (record, envelope):
            _reject()
        return record.original


def _reject() -> None:
    raise AdapterError('root_backup_origin_mismatch', 'root backup origin verification failed')
