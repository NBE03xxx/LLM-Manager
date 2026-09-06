from __future__ import annotations

import hashlib
from dataclasses import dataclass
from contextlib import AbstractContextManager
from typing import Protocol, Callable

from llm_manager.application.errors import AdapterError
from llm_manager.domain.models import utc_now

from .helper_protocol import HelperOperation, HelperOperationKind, HelperRequest, validate_request
from .helper_staging import HelperStagingStore


class HelperExecutionBackend(Protocol):
    """Fixed-operation backend implemented by the packaged privileged helper."""

    def locked(self) -> AbstractContextManager[int | None]: ...

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

    def __init__(self, staging: HelperStagingStore, backend: HelperExecutionBackend, *,
                 before_replace: Callable[[HelperRequest, int], None] | None = None) -> None:
        self.staging = staging
        self.backend = backend
        self.before_replace = before_replace

    def execute(self, request: HelperRequest, expected_hash: str) -> tuple[HelperOperationResult, ...]:
        validate_request(request, expected_hash, now=utc_now())
        try:
            with self.backend.locked() as target_fd:
                validate_request(request, expected_hash, now=utc_now())
                return self._execute_locked(request, target_fd)
        except (AdapterError, OSError) as error:
            code = error.code if isinstance(error, AdapterError) else 'helper_operation_failed'
            return tuple(HelperOperationResult(item.operation_id, item.kind, False,
                                               code if index == 0 else 'not_executed')
                         for index, item in enumerate(request.operations))

    def _execute_locked(self, request: HelperRequest, target_fd=None) -> tuple[HelperOperationResult, ...]:
        results: list[HelperOperationResult] = []
        for index, operation in enumerate(request.operations):
            try:
                self._execute(operation, request, target_fd)
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

    def _execute(self, operation: HelperOperation, request: HelperRequest, target_fd=None) -> None:
        if operation.kind in {
            HelperOperationKind.ATOMIC_REPLACE,
            HelperOperationKind.RESTORE_FILE,
            HelperOperationKind.REMOVE_CREATED_FILE,
        }:
            self._verify_before(operation)
        if operation.kind in {HelperOperationKind.ATOMIC_REPLACE, HelperOperationKind.RESTORE_FILE}:
            content = self.staging.verify(request, operation)
            if operation.kind is HelperOperationKind.ATOMIC_REPLACE and self.before_replace is not None:
                if type(target_fd) is not int:
                    raise AdapterError('root_capture_lock_missing', 'capture requires the locked target directory')
                self.before_replace(request, target_fd)
                validate_request(request, request.request_hash, now=utc_now())
                self._verify_before(operation)
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
