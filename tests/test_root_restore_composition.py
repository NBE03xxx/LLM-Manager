import os
import unittest
from contextlib import ExitStack
from unittest.mock import patch, Mock

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure import root_restore_composition as composition
from llm_manager.infrastructure.local_root_restore_preflight import CheckLocalRootRestore
from llm_manager.infrastructure.root_restore_store import RootRestoreState
from tests import test_root_restore_audit as fixture
from tests.test_local_root_restore_protocol import NOW

OPENERS = ('open_production_directory', 'open_production_key_directory',
           'open_production_source_parent', 'open_production_execution_directory',
           'open_production_audit_directory')


class RootRestoreCompositionTests(unittest.TestCase):
    def test_nonroot_rejected_before_opening_paths(self):
        with patch.object(composition.os, 'geteuid', return_value=1000), patch.object(composition, OPENERS[0]) as opener:
            with self.assertRaises(AdapterError):
                with composition.production_execution(): pass
            opener.assert_not_called()

    def test_every_partial_open_failure_closes_exactly_acquired_descriptors(self):
        for fail_at in range(len(OPENERS)):
            with self.subTest(fail_at=fail_at), ExitStack() as stack:
                stack.enter_context(patch.object(composition.os, 'geteuid', return_value=0))
                close = stack.enter_context(patch.object(composition.os, 'close'))
                for i, name in enumerate(OPENERS):
                    stack.enter_context(patch.object(composition, name, side_effect=OSError('unavailable') if i == fail_at else None, return_value=100+i))
                with self.assertRaises(OSError):
                    with composition.production_execution(): pass
                self.assertEqual([c.args[0] for c in close.call_args_list], list(reversed(range(100,100+fail_at))))

    def assembly(self, stack):
        stack.enter_context(patch.object(composition.os, 'geteuid', return_value=0))
        for i, name in enumerate(OPENERS):
            stack.enter_context(patch.object(composition, name, return_value=100+i))
        close = stack.enter_context(patch.object(composition.os, 'close'))
        audit = stack.enter_context(patch.object(composition, 'RootRestoreAuditLog')).return_value
        return close, audit

    def test_fixed_components_share_store_target_verifier_and_do_not_execute(self):
        with ExitStack() as stack:
            close, audit = self.assembly(stack)
            service = stack.enter_context(patch.object(composition, 'RootRestoreOllamaService')).return_value
            with composition.production_execution() as executor:
                evidence = executor.preflight.evidence
                self.assertIs(evidence.store, executor.store)
                self.assertIs(evidence.target, executor.target)
                self.assertIs(evidence.verifier, executor.verifier)
                self.assertIs(executor.verifier.reader, executor.origins)
                self.assertEqual(executor.target.owner_uid, 0)
                self.assertEqual(executor.store.reader.owner_uid, 0)
                audit.read_all.assert_called_once_with()
                audit.append.assert_not_called()
                service.reload_restart_validate.assert_not_called()
            self.assertEqual([c.args[0] for c in close.call_args_list], [104,103,102,101,100])

    def test_audit_rejection_and_body_failure_close_all_resources(self):
        for audit_failure in (True, False):
            with self.subTest(audit_failure=audit_failure), ExitStack() as stack:
                close, audit = self.assembly(stack)
                if audit_failure: audit.read_all.side_effect = AdapterError('invalid_audit', 'unavailable')
                with self.assertRaises((AdapterError, RuntimeError)):
                    with composition.production_execution(): raise RuntimeError('body failure')
                self.assertEqual([c.args[0] for c in close.call_args_list], [104,103,102,101,100])


class StoredRootRestorePreflightIntegrationTests(unittest.TestCase):
    setUp = fixture.RootRestoreAuditIntegrationTests.setUp
    run_capture = fixture.RootRestoreAuditIntegrationTests.run_capture
    prepare = fixture.RootRestoreAuditIntegrationTests.prepare
    make = fixture.RootRestoreAuditIntegrationTests.make
    run_restore = fixture.RootRestoreAuditIntegrationTests.run_restore
    attach = fixture.RootRestoreAuditIntegrationTests.attach

    def test_real_port_restores_with_strict_audit_and_blocks_replay(self):
        self.attach()
        port = composition.StoredRootRestorePreflight(self.store, self.backend, self.verifier)
        self.coordinator.preflight = CheckLocalRootRestore(port, clock=lambda: NOW)
        self.assertEqual(self.run_restore().state, RootRestoreState.COMMITTED)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(len(self.audit.read_all()), 2)
        with self.assertRaises(AdapterError): self.run_restore()

    def test_real_port_rejects_missing_key_without_attempt_or_mutation(self):
        self.attach()
        port = composition.StoredRootRestorePreflight(self.store, self.backend, self.verifier)
        self.coordinator.preflight = CheckLocalRootRestore(port, clock=lambda: NOW)
        (self.root/'keys/key-1.key').unlink()
        with self.assertRaises(AdapterError): self.run_restore()
        self.assertEqual(self.target.read_bytes(), b'new current settings')
        self.assertEqual(self.audit.read_all(), ())
        self.assertEqual(self.service.calls, 0)
