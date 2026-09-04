from __future__ import annotations

from dataclasses import dataclass, field, replace

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.optimization import stable_hash
from llm_manager.application.ports import CancellationToken, HostPort, PrivilegedHelperProbePort
from llm_manager.domain.models import DiagnosticReport, OptimizationPlan, utc_now
from llm_manager.planning import ConfigSnapshot, OllamaDropInPlanner, OpenCodeChangePlanner
from llm_manager.planning.ollama import DROP_IN_PATH


@dataclass(frozen=True, slots=True)
class BuildSelectedOpenCodeChangePlan:
    max_config_bytes: int = 1024 * 1024
    planner: OpenCodeChangePlanner = field(default_factory=OpenCodeChangePlanner)

    def execute(
        self,
        plan: OptimizationPlan,
        report: DiagnosticReport,
        host: HostPort,
        cancellation: CancellationToken,
    ) -> OptimizationPlan:
        if cancellation.cancelled:
            raise OperationCancelled("change planning cancelled")
        if plan.change_set is not None:
            raise AdapterError("change_set_already_generated", "plan already has a change set")
        if plan.report_id != report.report_id or plan.report_hash != stable_hash(report):
            raise AdapterError("stale_report", "plan is not bound to the diagnostic report")
        if plan.expires_at is not None and utc_now() >= plan.expires_at:
            raise AdapterError("stale_plan", "optimization plan has expired")
        if not plan.selected_ids:
            raise AdapterError("selection_required", "select at least one recommendation")

        recommendations = {item.recommendation_id: item for item in plan.recommendations}
        try:
            selected = tuple(recommendations[item_id] for item_id in plan.selected_ids)
        except KeyError as error:
            raise AdapterError("selection_invalid", "selected recommendation is missing") from error
        if any(not item.actionable or item.conflicts_with for item in selected):
            raise AdapterError("selection_invalid", "selected recommendation is not actionable")

        info = report.opencode
        if info is None or info.active_config is None:
            raise AdapterError("source_unavailable", "active OpenCode config is unavailable")
        if any(item.target != info.active_config for item in selected):
            raise AdapterError("unsupported_target", "selected target is not an OpenCode config")

        observed = host.identify(cancellation)
        if (
            observed.host_id != report.host.host_id
            or observed.kind is not report.host.kind
            or observed.fingerprint != report.host.fingerprint
        ):
            raise AdapterError("host_identity_changed", "host identity changed after diagnosis")
        try:
            content = host.read_file(info.active_config, self.max_config_bytes, cancellation).decode(
                "utf-8", errors="strict"
            )
        except UnicodeDecodeError as error:
            raise AdapterError("config_encoding_invalid", "OpenCode config is not UTF-8") from error
        change_set = self.planner.plan(
            report, selected, ConfigSnapshot.capture(info.active_config, content)
        )
        if not change_set.changes:
            raise AdapterError("empty_change_set", "selection produced no changes")
        return replace(plan, change_set=change_set)


@dataclass(frozen=True, slots=True)
class BuildSelectedOllamaChangePlan:
    """Build the fixed privileged Ollama drop-in after fresh read-only checks."""

    helper_probe: PrivilegedHelperProbePort
    max_config_bytes: int = 1024 * 1024
    planner: OllamaDropInPlanner = field(default_factory=OllamaDropInPlanner)

    def execute(
        self,
        plan: OptimizationPlan,
        report: DiagnosticReport,
        host: HostPort,
        cancellation: CancellationToken,
    ) -> OptimizationPlan:
        if cancellation.cancelled:
            raise OperationCancelled("change planning cancelled")
        if plan.change_set is not None:
            raise AdapterError("change_set_already_generated", "plan already has a change set")
        if plan.report_id != report.report_id or plan.report_hash != stable_hash(report):
            raise AdapterError("stale_report", "plan is not bound to the diagnostic report")
        if plan.expires_at is not None and utc_now() >= plan.expires_at:
            raise AdapterError("stale_plan", "optimization plan has expired")
        if not plan.selected_ids:
            raise AdapterError("selection_required", "select at least one recommendation")

        recommendations = {item.recommendation_id: item for item in plan.recommendations}
        try:
            selected = tuple(recommendations[item_id] for item_id in plan.selected_ids)
        except KeyError as error:
            raise AdapterError("selection_invalid", "selected recommendation is missing") from error
        if any(
            not item.actionable
            or item.conflicts_with
            or item.target != "ollama.systemd"
            or not item.requires_root
            for item in selected
        ):
            raise AdapterError("selection_invalid", "selected recommendation is not an actionable root Ollama setting")

        observed = host.identify(cancellation)
        if (
            observed.host_id != report.host.host_id
            or observed.kind is not report.host.kind
            or observed.fingerprint != report.host.fingerprint
        ):
            raise AdapterError("host_identity_changed", "host identity changed after diagnosis")
        if not self.helper_probe.root_apply_allowed(host, cancellation):
            raise AdapterError(
                "privileged_helper_unavailable",
                "compatible privileged helper is required for root changes",
            )

        target = host.stat(DROP_IN_PATH, cancellation)
        if target.path != DROP_IN_PATH or target.is_symlink:
            raise AdapterError("unsafe_target", "Ollama drop-in metadata is unsafe")
        content: str | None = None
        if target.exists:
            try:
                raw = host.read_file(DROP_IN_PATH, self.max_config_bytes, cancellation)
                content = raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError as error:
                raise AdapterError("config_encoding_invalid", "Ollama drop-in is not UTF-8") from error
        change_set = self.planner.plan(report, selected, content)
        if not change_set.changes:
            raise AdapterError("empty_change_set", "selection produced no changes")
        return replace(plan, change_set=change_set)
