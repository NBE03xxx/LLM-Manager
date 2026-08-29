from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from llm_manager.application.errors import AdapterError
from llm_manager.domain.models import utc_now

from .helper_protocol import HelperOperation, HelperOperationKind, HelperRequest, validate_request
from .helper_staging import HelperStagingStore


class HelperExecutionBackend(Protocol):
    """Fixed-operation backend implemented by the packaged privileged helper."""

    def read_file(self, target: str) -> bytes | None: ...

    def atomic_write(self, target: str, content: bytes, mode: int, uid: int, gid: int) -> None: ...

    def remove_file(self, target: str) -> None: ...

    def daemon_reload(self) -> None: ...

    def restart_unit(self, unit: str) -> None: ...


@dataclass(frozen=True, slots=True)
class HelperOperationResult:
    operation_id: str
    kind: HelperOperationKind
    completed: bool
    error_code: str | None = None


class DeclaredHelperExecutor:
    """Executes only decoded, allowlisted helper operations in declared order."""

    def __init__(self, staging: HelperStagingStore, backend: HelperExecutionBackend) -> None:
        self.staging = staging
        self.backend = backend

    def execute(self, request: HelperRequest, expected_hash: str) -> tuple[HelperOperationResult, ...]:
        validate_request(request, expected_hash, now=utc_now())
        results: list[HelperOperationResult] = []
        for index, operation in enumerate(request.operations):
            try:
                self._execute(operation, request)
            except AdapterError as error:
                results.append(HelperOperationResult(operation.operation_id, operation.kind, False, error.code))
                results.extend(
                    HelperOperationResult(item.operation_id, item.kind, False, "not_executed")
                    for item in request.operations[index + 1 :]
                )
                return tuple(results)
            except OSError:
                results.append(
                    HelperOperationResult(operation.operation_id, operation.kind, False, "helper_operation_failed")
                )
                results.extend(
                    HelperOperationResult(item.operation_id, item.kind, False, "not_executed")
                    for item in request.operations[index + 1 :]
                )
                return tuple(results)
            results.append(HelperOperationResult(operation.operation_id, operation.kind, True))
        return tuple(results)

    def _execute(self, operation: HelperOperation, request: HelperRequest) -> None:
        if operation.kind in {
            HelperOperationKind.ATOMIC_REPLACE,
            HelperOperationKind.RESTORE_FILE,
            HelperOperationKind.REMOVE_CREATED_FILE,
        }:
            self._verify_before(operation)
        if operation.kind in {HelperOperationKind.ATOMIC_REPLACE, HelperOperationKind.RESTORE_FILE}:
            content = self.staging.verify(request, operation)
            self.backend.atomic_write(
                operation.target,  # type: ignore[arg-type]
                content,
                operation.expected_mode,  # type: ignore[arg-type]
                operation.expected_uid,  # type: ignore[arg-type]
                operation.expected_gid,  # type: ignore[arg-type]
            )
        elif operation.kind is HelperOperationKind.REMOVE_CREATED_FILE:
            self.backend.remove_file(operation.target)  # type: ignore[arg-type]
        elif operation.kind is HelperOperationKind.DAEMON_RELOAD:
            self.backend.daemon_reload()
        elif operation.kind is HelperOperationKind.RESTART_UNIT:
            self.backend.restart_unit(operation.unit)  # type: ignore[arg-type]
        else:
            raise AdapterError("unknown_operation", "helper operation is unsupported")

    def _verify_before(self, operation: HelperOperation) -> None:
        current = self.backend.read_file(operation.target)  # type: ignore[arg-type]
        if operation.before_hash is None:
            if current is not None:
                raise AdapterError("stale_helper_target", "helper target unexpectedly exists")
            return
        if current is None or hashlib.sha256(current).hexdigest() != operation.before_hash:
            raise AdapterError("stale_helper_target", "helper target changed after approval")
