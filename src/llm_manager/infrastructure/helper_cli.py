from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.domain.models import utc_now

from .helper_backend import LocalSystemHelperBackend
from .helper_executor import DeclaredHelperExecutor, HelperExecutionBackend, HelperOperationResult
from .helper_protocol import MAX_REQUEST_BYTES, decode_request
from .helper_receipts import HelperReceiptStore
from .helper_staging import HelperStagingStore

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llm-manager-helper", allow_abbrev=False)
    parser.add_argument("operation_id")
    parser.add_argument("expected_hash")
    arguments = parser.parse_args(argv)
    try:
        results = run_helper(arguments.operation_id, arguments.expected_hash)
    except AdapterError as error:
        _write({"status": "failed", "error_code": error.code})
        return 1
    _write(
        {
            "status": "completed" if all(item.completed for item in results) else "failed",
            "operations": [
                {
                    "operation_id": item.operation_id,
                    "kind": item.kind.value,
                    "completed": item.completed,
                    "error_code": item.error_code,
                }
                for item in results
            ],
        }
    )
    return 0 if all(item.completed for item in results) else 1


def run_helper(
    operation_id: str,
    expected_hash: str,
    *,
    environ: dict[str, str] | None = None,
    runtime_base: Path = Path("/run/user"),
    backend: HelperExecutionBackend | None = None,
    receipts: HelperReceiptStore | None = None,
    effective_uid: int | None = None,
) -> tuple[HelperOperationResult, ...]:
    if not _IDENTIFIER.fullmatch(operation_id) or not _DIGEST.fullmatch(expected_hash):
        raise AdapterError("invalid_helper_argument", "helper arguments are invalid")
    uid = _invoking_uid(environ if environ is not None else dict(os.environ))
    if (os.geteuid() if effective_uid is None else effective_uid) != 0:
        raise AdapterError("root_required", "helper must run with effective UID 0")
    staging_root = runtime_base / str(uid) / "llm-manager" / "helper"
    staging = HelperStagingStore(staging_root, owner_uid=uid)
    request_path = staging_root / operation_id / "request.json"
    content = _read_user_request(request_path, uid)
    request = decode_request(content, expected_hash=expected_hash, now=utc_now())
    if request.operation_id != operation_id:
        raise AdapterError("operation_mismatch", "request does not match the invoked operation")
    executor = DeclaredHelperExecutor(staging, backend or LocalSystemHelperBackend())
    receipt_store = receipts or HelperReceiptStore()
    receipt_store.begin(request)
    results = executor.execute(request, expected_hash)
    receipt_store.finish(request, results)
    return results


def _invoking_uid(environ: dict[str, str]) -> int:
    values = [environ.get(name) for name in ("PKEXEC_UID", "SUDO_UID") if environ.get(name) is not None]
    if len(values) != 1 or not values[0].isdigit():
        raise AdapterError("invalid_invoking_user", "exactly one trusted invoking UID is required")
    uid = int(values[0])
    if uid < 0 or uid == 0:
        raise AdapterError("invalid_invoking_user", "invoking UID must identify a non-root user")
    return uid


def _read_user_request(path: Path, owner_uid: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise AdapterError("unsafe_request", "helper request could not be opened safely") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise AdapterError("unsafe_request", "helper request is not a regular file")
        if metadata.st_uid != owner_uid or stat.S_IMODE(metadata.st_mode) != 0o600:
            raise AdapterError("unsafe_request", "helper request owner or mode is unsafe")
        if metadata.st_size > MAX_REQUEST_BYTES:
            raise AdapterError("request_too_large", "helper request exceeds 1 MiB")
        chunks: list[bytes] = []
        remaining = MAX_REQUEST_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
    finally:
        os.close(descriptor)
    if len(content) > MAX_REQUEST_BYTES:
        raise AdapterError("request_too_large", "helper request exceeds 1 MiB")
    return content


def _write(value: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
