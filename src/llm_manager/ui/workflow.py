from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from llm_manager.domain.enums import ReportStatus
from llm_manager.domain.models import DiagnosticReport, utc_now


class GuiStep(StrEnum):
    HOSTS = "hosts"
    DIAGNOSE = "diagnose"
    RECOMMENDATIONS = "recommendations"
    REVIEW = "review"
    RESULTS = "results"
    BACKUPS = "backups"


class WorkflowStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PARTIAL = "partial"
    SUCCESS = "success"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"


@dataclass(frozen=True, slots=True)
class GuiState:
    step: GuiStep = GuiStep.HOSTS
    status: WorkflowStatus = WorkflowStatus.IDLE
    selected_host_id: str | None = None
    report: DiagnosticReport | None = None
    plan_hash: str | None = None
    approved_plan_hash: str | None = None
    plan_expires_at: datetime | None = None
    error_code: str | None = None

    @property
    def busy(self) -> bool:
        return self.status in (WorkflowStatus.RUNNING, WorkflowStatus.CANCEL_REQUESTED)

    @property
    def approved(self) -> bool:
        return self.plan_hash is not None and self.plan_hash == self.approved_plan_hash


class GuiPresenter:
    def __init__(self) -> None:
        self._state = GuiState()

    @property
    def state(self) -> GuiState:
        return self._state

    def select_host(self, host_id: str) -> GuiState:
        if self._state.busy:
            raise RuntimeError("workflow_busy")
        if not host_id.strip():
            raise ValueError("host_id must not be blank")
        if host_id != self._state.selected_host_id:
            self._state = GuiState(selected_host_id=host_id)
        return self._state

    def begin_diagnosis(self) -> GuiState:
        if self._state.busy:
            raise RuntimeError("workflow_busy")
        if self._state.selected_host_id is None:
            raise RuntimeError("host_required")
        self._state = replace(
            self._state,
            step=GuiStep.DIAGNOSE,
            status=WorkflowStatus.RUNNING,
            report=None,
            plan_hash=None,
            approved_plan_hash=None,
            plan_expires_at=None,
            error_code=None,
        )
        return self._state

    def request_cancel(self) -> GuiState:
        if self._state.status is not WorkflowStatus.RUNNING:
            return self._state
        self._state = replace(self._state, status=WorkflowStatus.CANCEL_REQUESTED)
        return self._state

    def finish_diagnosis(self, report: DiagnosticReport) -> GuiState:
        if not self._state.busy:
            raise RuntimeError("diagnosis_not_running")
        if report.host.host_id != self._state.selected_host_id:
            raise ValueError("report_host_mismatch")
        status = {
            ReportStatus.COMPLETE: WorkflowStatus.SUCCESS,
            ReportStatus.PARTIAL: WorkflowStatus.PARTIAL,
            ReportStatus.FAILED: WorkflowStatus.FAILED,
        }[report.status]
        step = GuiStep.RECOMMENDATIONS if report.status is not ReportStatus.FAILED else GuiStep.DIAGNOSE
        self._state = replace(self._state, step=step, status=status, report=report, error_code=None)
        return self._state

    def fail_diagnosis(self, error_code: str) -> GuiState:
        if not self._state.busy:
            raise RuntimeError("diagnosis_not_running")
        self._state = replace(
            self._state,
            step=GuiStep.DIAGNOSE,
            status=WorkflowStatus.FAILED,
            error_code=error_code,
        )
        return self._state

    def review_plan(self, plan_hash: str) -> GuiState:
        if self._state.busy:
            raise RuntimeError("workflow_busy")
        if self._state.report is None:
            raise RuntimeError("report_required")
        if not plan_hash.strip():
            raise ValueError("plan_hash must not be blank")
        approved_hash = self._state.approved_plan_hash if plan_hash == self._state.plan_hash else None
        self._state = replace(
            self._state,
            step=GuiStep.REVIEW,
            plan_hash=plan_hash,
            approved_plan_hash=approved_hash,
            error_code=None,
        )
        return self._state

    def begin_change_plan(self, plan_hash: str) -> GuiState:
        self.review_plan(plan_hash)
        self._state = replace(self._state, status=WorkflowStatus.RUNNING)
        return self._state

    def finish_change_plan(
        self,
        change_set_hash: str,
        expires_at: datetime | None = None,
        now: datetime | None = None,
    ) -> GuiState:
        if not self._state.busy:
            raise RuntimeError("change_planning_not_running")
        if not change_set_hash.strip():
            raise ValueError("change_set_hash must not be blank")
        if expires_at is not None and (now or utc_now()) >= expires_at:
            return self.fail_change_plan("stale_plan")
        self._state = replace(
            self._state,
            step=GuiStep.REVIEW,
            status=WorkflowStatus.SUCCESS,
            plan_hash=change_set_hash,
            approved_plan_hash=None,
            plan_expires_at=expires_at,
            error_code=None,
        )
        return self._state

    def fail_change_plan(self, error_code: str) -> GuiState:
        if not self._state.busy:
            raise RuntimeError("change_planning_not_running")
        self._state = replace(
            self._state,
            step=GuiStep.REVIEW,
            status=WorkflowStatus.FAILED,
            approved_plan_hash=None,
            plan_expires_at=None,
            error_code=error_code,
        )
        return self._state

    def approve_plan(self, now: datetime | None = None) -> GuiState:
        if self._state.plan_hash is None:
            raise RuntimeError("plan_required")
        if self._state.plan_expires_at is not None and (now or utc_now()) >= self._state.plan_expires_at:
            self.expire_plan()
            raise RuntimeError("stale_plan")
        self._state = replace(self._state, approved_plan_hash=self._state.plan_hash)
        return self._state

    def revoke_plan(self) -> GuiState:
        self._state = replace(self._state, approved_plan_hash=None)
        return self._state

    def invalidate_plan(self) -> GuiState:
        if self._state.busy:
            raise RuntimeError("workflow_busy")
        self._state = replace(
            self._state,
            plan_hash=None,
            approved_plan_hash=None,
            plan_expires_at=None,
            error_code=None,
        )
        return self._state

    def expire_plan(self) -> GuiState:
        self._state = replace(
            self._state,
            status=WorkflowStatus.FAILED,
            approved_plan_hash=None,
            error_code="stale_plan",
        )
        return self._state
