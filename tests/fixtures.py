from datetime import UTC, datetime, timedelta

from llm_manager.domain.enums import ChangeOperation, HostKind, PlanStatus, ProbeStatus, ReportStatus
from llm_manager.domain.models import (
    BackupManifest,
    Change,
    ChangeSet,
    DiagnosticReport,
    EncryptionInfo,
    HostCapabilities,
    HostInfo,
    LocalizedMessage,
    OllamaInfo,
    OpenCodeInfo,
    OptimizationPlan,
    OptimizationProfile,
)


def host_info(kind: HostKind = HostKind.LOCAL) -> HostInfo:
    return HostInfo(
        host_id="host-1",
        kind=kind,
        display_name="Test host",
        ssh_alias="test-box" if kind is HostKind.SSH else None,
        capabilities=HostCapabilities(can_execute=True, can_read_files=True),
    )


def report() -> DiagnosticReport:
    return DiagnosticReport(
        report_id="report-1",
        schema_version="1.0",
        host=host_info(),
        status=ReportStatus.COMPLETE,
        ollama=OllamaInfo(installed=True, version="0.33.2", api_connectivity=ProbeStatus.OK),
        opencode=OpenCodeInfo(installed=True, version="1.18.25"),
    )


def change_set() -> ChangeSet:
    change = Change(
        change_id="change-1",
        target="/tmp/example",
        operation=ChangeOperation.REPLACE_FILE,
        before="old",
        after="new",
        before_hash="before-hash",
        diff="-old\n+new",
    )
    return ChangeSet(
        change_set_id="changes-1",
        host_id="host-1",
        changes=(change,),
        content_hash="changes-hash",
        status=PlanStatus.DRAFT,
    )


def plan() -> OptimizationPlan:
    return OptimizationPlan(
        plan_id="plan-1",
        report_id="report-1",
        report_hash="report-hash",
        profile=OptimizationProfile(
            profile_id="agent",
            version=1,
            name="Agent",
            goals=("stability",),
        ),
        rule_catalog_version="1",
        recommendations=(),
        selected_ids=(),
        change_set=change_set(),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )


def manifest() -> BackupManifest:
    return BackupManifest(
        backup_id="backup-1",
        schema_version="1.0",
        plan_id="plan-1",
        change_set_hash="c" * 64,
        host_id="host-1",
        host_fingerprint="fingerprint",
        items=(),
        manifest_hash="manifest-hash",
        storage_location="/tmp/backups",
        encryption=EncryptionInfo(enabled=False),
        complete=True,
    )


def message(key: str = "test.message") -> LocalizedMessage:
    return LocalizedMessage(key, fallback_text="Test message")
