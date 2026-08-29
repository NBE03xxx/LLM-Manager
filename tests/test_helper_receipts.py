import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure.helper_executor import HelperOperationResult
from llm_manager.infrastructure.helper_protocol import HelperOperation, HelperOperationKind, HelperRequest
from llm_manager.infrastructure.helper_receipts import HelperReceiptStatus, HelperReceiptStore


def _request(operation_id="operation-1", request_hash_seed="a"):
    now = datetime.now(UTC)
    request = HelperRequest(
        1, operation_id, "host-1", "plan-1", request_hash_seed * 64,
        (HelperOperation("reload-1", HelperOperationKind.DAEMON_RELOAD),),
        now, now + timedelta(minutes=5),
    )
    return request.with_hash()


class HelperReceiptStoreTests(unittest.TestCase):
    def test_claim_finalize_reload_and_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "receipts"
            store = HelperReceiptStore(root, sandbox=True)
            request = _request()
            self.assertEqual(store.begin(request).status, HelperReceiptStatus.EXECUTING)
            result = HelperOperationResult("reload-1", HelperOperationKind.DAEMON_RELOAD, True)
            receipt = store.finish(request, (result,))
            self.assertEqual(receipt.status, HelperReceiptStatus.COMPLETED)
            self.assertEqual(store.load(request.operation_id), receipt)
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            self.assertEqual((root / "operation-1.json").stat().st_mode & 0o777, 0o600)

    def test_rejects_replay_and_operation_id_collision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = HelperReceiptStore(Path(directory) / "receipts", sandbox=True)
            request = _request()
            store.begin(request)
            with self.assertRaisesRegex(AdapterError, "already claimed"):
                store.begin(request)
            collision = _request(request_hash_seed="b")
            with self.assertRaises(AdapterError) as raised:
                store.begin(collision)
            self.assertEqual(raised.exception.code, "operation_id_collision")

    def test_failed_result_is_terminal_and_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "receipts"
            store = HelperReceiptStore(root, sandbox=True)
            request = _request()
            store.begin(request)
            failed = HelperOperationResult("reload-1", HelperOperationKind.DAEMON_RELOAD, False, "injected")
            self.assertEqual(store.finish(request, (failed,)).status, HelperReceiptStatus.FAILED)
            with self.assertRaises(AdapterError):
                store.finish(request, (failed,))
            (root / "operation-1.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(AdapterError):
                store.load(request.operation_id)


if __name__ == "__main__":
    unittest.main()
