from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from llm_manager.application.errors import AdapterError

from .backup import _atomic_write, _fsync_directory
from .helper_executor import HelperOperationResult
from .helper_protocol import HelperRequest


class HelperReceiptStatus(StrEnum):
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class HelperReceipt:
    operation_id: str
    request_hash: str
    status: HelperReceiptStatus
    results: tuple[tuple[str, str, bool, str | None], ...] = ()


class HelperReceiptStore:
    """Root-owned replay barrier and terminal helper result store."""

    def __init__(self, root: Path = Path("/var/lib/llm-manager/helper-receipts"), *, sandbox: bool = False) -> None:
        self.root = root.absolute()
        self.sandbox = sandbox
        if self.root != Path("/var/lib/llm-manager/helper-receipts") and not sandbox:
            raise ValueError("alternate receipt root requires explicit sandbox mode")

    def begin(self, request: HelperRequest) -> HelperReceipt:
        self._prepare_root()
        receipt = HelperReceipt(request.operation_id, request.request_hash, HelperReceiptStatus.EXECUTING)
        path = self._path(request.operation_id)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError as error:
            existing = self.load(request.operation_id)
            code = "replayed_request" if existing.request_hash == request.request_hash else "operation_id_collision"
            raise AdapterError(code, "helper operation was already claimed") from error
        try:
            content = _bytes(receipt)
            written = 0
            while written < len(content):
                written += os.write(descriptor, content[written:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _fsync_directory(self.root)
        return receipt

    def finish(self, request: HelperRequest, results: tuple[HelperOperationResult, ...]) -> HelperReceipt:
        current = self.load(request.operation_id)
        if current.request_hash != request.request_hash or current.status is not HelperReceiptStatus.EXECUTING:
            raise AdapterError("invalid_receipt_transition", "helper receipt cannot be finalized")
        completed = bool(results) and all(item.completed for item in results)
        receipt = HelperReceipt(
            request.operation_id,
            request.request_hash,
            HelperReceiptStatus.COMPLETED if completed else HelperReceiptStatus.FAILED,
            tuple((item.operation_id, item.kind.value, item.completed, item.error_code) for item in results),
        )
        _atomic_write(self._path(request.operation_id), _bytes(receipt), 0o600)
        return receipt

    def load(self, operation_id: str) -> HelperReceipt:
        path = self._path(operation_id)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise AdapterError("invalid_receipt", "helper receipt is missing or unsafe") from error
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
                raise AdapterError("invalid_receipt", "helper receipt metadata is unsafe")
            if not self.sandbox and metadata.st_uid != 0:
                raise AdapterError("invalid_receipt", "helper receipt is not root-owned")
            chunks: list[bytes] = []
            remaining = 1024 * 1024 + 1
            while remaining:
                chunk = os.read(descriptor, remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            content = b"".join(chunks)
        finally:
            os.close(descriptor)
        if len(content) > 1024 * 1024:
            raise AdapterError("invalid_receipt", "helper receipt is too large")
        try:
            value = json.loads(content.decode("utf-8"))
            receipt = _decode(value)
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise AdapterError("invalid_receipt", "helper receipt is malformed") from error
        if receipt.operation_id != operation_id or _bytes(receipt) != content:
            raise AdapterError("invalid_receipt", "helper receipt identity or encoding is invalid")
        return receipt

    def _prepare_root(self) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise AdapterError("unsafe_receipt_root", "helper receipt root is unsafe")
        os.chmod(self.root, 0o700)
        metadata = self.root.stat(follow_symlinks=False)
        if not self.sandbox and metadata.st_uid != 0:
            raise AdapterError("unsafe_receipt_root", "helper receipt root is not root-owned")

    def _path(self, operation_id: str) -> Path:
        if not operation_id or Path(operation_id).name != operation_id or operation_id in {".", ".."}:
            raise AdapterError("invalid_operation_id", "receipt operation ID is invalid")
        return self.root / f"{operation_id}.json"


def _bytes(receipt: HelperReceipt) -> bytes:
    value = {
        "operation_id": receipt.operation_id,
        "request_hash": receipt.request_hash,
        "results": [
            {"operation_id": item[0], "kind": item[1], "completed": item[2], "error_code": item[3]}
            for item in receipt.results
        ],
        "status": receipt.status.value,
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode(value: object) -> HelperReceipt:
    if not isinstance(value, dict) or set(value) != {"operation_id", "request_hash", "results", "status"}:
        raise ValueError("invalid receipt fields")
    if not isinstance(value["operation_id"], str) or not isinstance(value["request_hash"], str):
        raise ValueError("invalid receipt identity")
    raw_results = value["results"]
    if not isinstance(raw_results, list):
        raise ValueError("invalid receipt results")
    results = []
    for item in raw_results:
        if not isinstance(item, dict) or set(item) != {"operation_id", "kind", "completed", "error_code"}:
            raise ValueError("invalid receipt result")
        if not isinstance(item["operation_id"], str) or not isinstance(item["kind"], str):
            raise ValueError("invalid receipt result identity")
        if type(item["completed"]) is not bool or item["error_code"] is not None and not isinstance(item["error_code"], str):
            raise ValueError("invalid receipt result state")
        results.append((item["operation_id"], item["kind"], item["completed"], item["error_code"]))
    return HelperReceipt(value["operation_id"], value["request_hash"], HelperReceiptStatus(value["status"]), tuple(results))
