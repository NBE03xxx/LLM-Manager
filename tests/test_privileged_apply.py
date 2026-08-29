import hashlib
import unittest
from dataclasses import replace

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.enums import ChangeOperation
from llm_manager.domain.models import ApprovalRecord, Change, ChangeSet
from llm_manager.infrastructure.privileged_apply import ApprovedHelperRequestFactory, LocalPrivilegedApplyService
from llm_manager.planning.ollama import DROP_IN_PATH
from tests.fixtures import plan


def _approved():
    content = '[Service]\nEnvironment="OLLAMA_HOST=127.0.0.1:11434"\n'
    change = Change(
        "ollama-change", DROP_IN_PATH, ChangeOperation.CREATE_FILE, "absent",
        (("OLLAMA_HOST", "127.0.0.1:11434"),), None, "diff",
        requires_root=True, requires_restart=True,
        rollback_operation=ChangeOperation.REMOVE_CREATED_FILE,
        validation_checks=("systemd.daemon_reload", "ollama.service.active"),
        replacement_text=content,
    )
    changes = ChangeSet("ollama-changes", "host-1", (change,), "b" * 64, affected_services=("ollama.service",))
    current = replace(plan(), change_set=changes)
    approval = ApprovalRecord("approval", current.plan_id, current.report_hash, changes.content_hash, "tester", current.backup_policy.content_hash, True)
    return current, approval, content


class ApprovedHelperRequestFactoryTests(unittest.TestCase):
    def test_binds_approved_plan_and_builds_fixed_operation_sequence(self) -> None:
        current, approval, content = _approved()
        prepared = ApprovedHelperRequestFactory().prepare(current, approval, "operation-1")
        request = prepared.request
        self.assertEqual(request.plan_id, current.plan_id)
        self.assertEqual(request.change_set_hash, current.change_set.content_hash)
        self.assertEqual([item.kind.value for item in request.operations], ["atomic_replace", "daemon_reload", "restart_unit"])
        self.assertEqual(request.operations[0].target, DROP_IN_PATH)
        self.assertEqual(request.operations[0].staged_content_hash, hashlib.sha256(content.encode()).hexdigest())
        self.assertEqual(prepared.staged_contents, (("operation-1:write", content.encode()),))

    def test_rejects_invalid_approval_and_non_allowlisted_plan(self) -> None:
        current, approval, _ = _approved()
        with self.assertRaises(AdapterError):
            ApprovedHelperRequestFactory().prepare(current, replace(approval, change_set_hash="c" * 64), "operation-1")
        unsafe_change = replace(current.change_set.changes[0], target="/etc/passwd")
        unsafe_set = replace(current.change_set, changes=(unsafe_change,))
        with self.assertRaises(AdapterError):
            ApprovedHelperRequestFactory().prepare(replace(current, change_set=unsafe_set), approval, "operation-1")

    def test_service_passes_only_prepared_request_to_invoker(self) -> None:
        current, approval, _ = _approved()
        invoker = _Invoker()
        results = LocalPrivilegedApplyService(ApprovedHelperRequestFactory(), invoker).execute(current, approval, "operation-1", CancellationToken())
        self.assertEqual(results, ())
        self.assertEqual(invoker.request.plan_id, current.plan_id)
        self.assertEqual(invoker.contents[0][0], "operation-1:write")


class _Invoker:
    def invoke(self, request, staged_contents, cancellation):
        self.request = request
        self.contents = staged_contents
        return ()


if __name__ == "__main__":
    unittest.main()
