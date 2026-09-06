"""Bounded root-backup selection and explicit review-to-execute handoff."""
from __future__ import annotations

import os

from llm_manager.application.errors import AdapterError
from llm_manager.domain.enums import HostKind
from llm_manager.infrastructure.root_backup_evidence import RootBackupInventoryItem
from llm_manager.infrastructure.root_restore_execute_client import RootRestoreExecuteClient
from llm_manager.infrastructure.root_restore_review_client import RootRestoreReviewClient
from .root_restore_execution import RootRestoreExecutionSession
from .root_restore_review import RootRestoreReviewSession


class RootRestoreInventorySession:
    def __init__(self, review_client, execute_client):
        if ((review_client.caller_uid, review_client.host_id)
                != (execute_client.caller_uid, execute_client.host_id)):
            raise AdapterError('root_restore_identity_mismatch',
                               'root restore clients have different identities')
        self.review_client = review_client
        self.execute_client = execute_client
        self.state = 'new'
        self.items = ()
        self.selected_backup_id = None
        self._list_started = False

    def list_task(self):
        if self.state != 'new' or self._list_started:
            raise AdapterError('root_inventory_state_invalid',
                               'root backup inventory cannot be loaded again')
        self._list_started = True
        self.state = 'loading'
        return lambda token: self.review_client.list_backups(token)

    def receive_inventory(self, items):
        if self.state != 'loading' or not isinstance(items, tuple) or len(items) > 32:
            self.fail()
            raise AdapterError('invalid_root_backup_inventory', 'invalid root backup inventory')
        if any(not isinstance(item, RootBackupInventoryItem)
               or item.host_id != self.review_client.host_id for item in items):
            self.fail()
            raise AdapterError('invalid_root_backup_inventory', 'invalid root backup inventory')
        identifiers = tuple(item.backup_id for item in items)
        if identifiers != tuple(sorted(identifiers)) or len(set(identifiers)) != len(identifiers):
            self.fail()
            raise AdapterError('invalid_root_backup_inventory', 'invalid root backup inventory')
        self.items = items
        self.state = 'empty' if not items else 'ready'

    def select(self, backup_id):
        self.selected_backup_id = None
        if self.state != 'ready' or not isinstance(backup_id, str):
            return
        if sum(item.backup_id == backup_id for item in self.items) == 1:
            self.selected_backup_id = backup_id

    @property
    def can_review(self):
        return self.state == 'ready' and self.selected_backup_id is not None

    def create_review_session(self):
        if not self.can_review:
            raise AdapterError('root_backup_selection_required',
                               'select one root backup before review')
        return RootRestoreReviewSession(self.review_client, self.selected_backup_id)

    def create_execution_session(self, review_session):
        if (not isinstance(review_session, RootRestoreReviewSession)
                or review_session.client is not self.review_client):
            raise AdapterError('root_restore_review_mismatch',
                               'execution requires this inventory review')
        request = review_session.approved_request_for_execution()
        return RootRestoreExecutionSession(
            self.execute_client, self.review_client, request,
            clock=review_session.clock,
        )

    def fail(self):
        self.state = 'failed'
        self.items = ()
        self.selected_backup_id = None


def production_inventory_session(host):
    host_id = 'local:' + os.uname().nodename
    if host.kind is not HostKind.LOCAL or host.host_id != host_id or os.getuid() == 0:
        raise AdapterError('root_inventory_requires_local_user',
                           'local user root inventory required')
    review = RootRestoreReviewClient(caller_uid=os.getuid(), host_id=host_id)
    execute = RootRestoreExecuteClient(caller_uid=os.getuid(), host_id=host_id)
    return RootRestoreInventorySession(review, execute)


def run_production_restore_workflow(host, *, locale='en', parent=None):
    """Explicit three-dialog workflow; caller must still pass availability Gate."""
    from .qt_root_restore_inventory import RootRestoreInventoryDialog
    from .qt_root_restore_review import RootRestoreReviewDialog
    from .qt_root_restore_execution import RootRestoreExecutionDialog
    session = production_inventory_session(host)
    inventory = RootRestoreInventoryDialog(session, locale=locale, parent=parent)
    if not inventory.exec():
        return
    review_session = session.create_review_session()
    review = RootRestoreReviewDialog(review_session, locale=locale, parent=parent,
                                     allow_execution_handoff=True)
    if not review.exec():
        return
    execution = RootRestoreExecutionDialog(
        session.create_execution_session(review_session), locale=locale, parent=parent,
    )
    execution.exec()
