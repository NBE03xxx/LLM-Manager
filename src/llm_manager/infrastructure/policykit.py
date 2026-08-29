from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken, CommandRequest, CommandResult

from .helper_executor import HelperOperationResult
from .helper_protocol import HelperOperationKind, HelperRequest
from .helper_staging import HelperStagingStore

PKEXEC = "/usr/bin/pkexec"
HELPER = "/usr/bin/llm-manager-helper"


class PolicyKitRunner(Protocol):
    def run(self, request: CommandRequest, cancellation: CancellationToken) -> CommandResult: ...


@dataclass(slots=True)
class LocalPolicyKitInvoker:
    staging: HelperStagingStore
    runner: PolicyKitRunner
    timeout_ms: int = 120_000

    def invoke(
        self,
        request: HelperRequest,
        staged_contents: tuple[tuple[str, bytes], ...],
        cancellation: CancellationToken,
    ) -> tuple[HelperOperationResult, ...]:
        expected = {
            item.operation_id
            for item in request.operations
            if item.kind in {HelperOperationKind.ATOMIC_REPLACE, HelperOperationKind.RESTORE_FILE}
        }
        supplied = {operation_id for operation_id, _ in staged_contents}
        if len(supplied) != len(staged_contents) or supplied != expected:
            raise AdapterError("invalid_staged_contents", "staged content IDs do not match helper operations")
        for operation_id, content in staged_contents:
            self.staging.stage(request, operation_id, content)
        self.staging.stage_request(request)
        command = CommandRequest(
            (PKEXEC, HELPER, request.operation_id, request.request_hash),
            self.timeout_ms,
            request.operation_id,
        )
        result = self.runner.run(command, cancellation)
        if result.timed_out:
            raise AdapterError("helper_timeout", "privileged helper timed out")
        if result.exit_code == 126:
            raise AdapterError("privilege_denied", "PolicyKit authentication was denied or dismissed")
        if result.exit_code == 127:
            raise AdapterError("helper_launch_failed", "PolicyKit could not launch the privileged helper")
        if result.exit_code not in {0, 1}:
            raise AdapterError("helper_failed", "privileged helper ended unexpectedly")
        parsed = _decode_result(result.stdout, request)
        succeeded = bool(parsed) and all(item.completed for item in parsed)
        if (result.exit_code == 0) != succeeded:
            raise AdapterError("invalid_helper_result", "helper exit status contradicts its result")
        return parsed


def _decode_result(content: str, request: HelperRequest) -> tuple[HelperOperationResult, ...]:
    if len(content.encode("utf-8")) > 1024 * 1024:
        raise AdapterError("invalid_helper_result", "helper result exceeds 1 MiB")
    try:
        value = json.loads(content)
    except json.JSONDecodeError as error:
        raise AdapterError("invalid_helper_result", "helper result is not JSON") from error
    if not isinstance(value, dict) or set(value) != {"operations", "status"}:
        raise AdapterError("invalid_helper_result", "helper result fields are invalid")
    if value["status"] not in {"completed", "failed"} or not isinstance(value["operations"], list):
        raise AdapterError("invalid_helper_result", "helper result state is invalid")
    results: list[HelperOperationResult] = []
    for raw in value["operations"]:
        if not isinstance(raw, dict) or set(raw) != {"completed", "error_code", "kind", "operation_id"}:
            raise AdapterError("invalid_helper_result", "helper operation result fields are invalid")
        if type(raw["completed"]) is not bool or raw["error_code"] is not None and not isinstance(raw["error_code"], str):
            raise AdapterError("invalid_helper_result", "helper operation result state is invalid")
        try:
            results.append(
                HelperOperationResult(
                    raw["operation_id"], HelperOperationKind(raw["kind"]), raw["completed"], raw["error_code"]
                )
            )
        except (TypeError, ValueError) as error:
            raise AdapterError("invalid_helper_result", "helper operation result identity is invalid") from error
    expected = [(item.operation_id, item.kind) for item in request.operations]
    if [(item.operation_id, item.kind) for item in results] != expected:
        raise AdapterError("invalid_helper_result", "helper result does not match the request")
    if (value["status"] == "completed") != all(item.completed for item in results):
        raise AdapterError("invalid_helper_result", "helper result summary is inconsistent")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    if canonical != content:
        raise AdapterError("invalid_helper_result", "helper result is not canonical")
    return tuple(results)
