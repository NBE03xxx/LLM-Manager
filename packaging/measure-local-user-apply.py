"""Phase 6 isolated local-user production Apply composition baseline.

Run from a source checkout with PYTHONPATH=src. Every sample uses a fresh
temporary config/state root and an in-memory test key; no user configuration or
Secret Service item is read or changed.
"""
from __future__ import annotations

import hashlib
import json
import platform
import resource
import sys
import tempfile
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.host_discovery import HostCandidate
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.enums import ChangeOperation, HostKind, PlanStatus, Severity, ValidationStatus
from llm_manager.domain.models import (
    ApprovalRecord,
    Change,
    ChangeSet,
    EncryptionInfo,
    LocalizedMessage,
    OptimizationPlan,
    OptimizationProfile,
    ValidationResult,
)
from llm_manager.infrastructure.backup import LocalBackupStore
from llm_manager.infrastructure.process import ProcessPolicy, SubprocessRunner
from llm_manager.ui.composition import LocalUserApplyTaskFactory


class GateKeys:
    def get_key(self, _reference: str, _scope: str) -> bytes:
        return b"k" * 32


class FailingRuntime:
    def validate(self, _changes, _cancellation):
        return (ValidationResult(
            "gate.runtime", "runtime", "gate.runtime", ValidationStatus.FAILED,
            "passed", "failed", Severity.HIGH, LocalizedMessage("gate.runtime.failed"),
        ),)


class RestoreFailingStore(LocalBackupStore):
    def restore(self, _manifest, _cancellation):
        raise AdapterError("gate_restore_failed", "injected restore failure")


def sample(expected: PlanStatus) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="llm-manager-local-apply-") as directory:
        root = Path(directory)
        config = root / "config"
        target_root = config / "opencode"
        target_root.mkdir(parents=True)
        target = target_root / "opencode.json"
        original = '{"model":"old"}'
        replacement = '{"model":"new"}'
        target.write_text(original, encoding="utf-8")
        change = Change(
            "change-local", str(target), ChangeOperation.REPLACE_FILE,
            "old", "new", hashlib.sha256(original.encode()).hexdigest(), "masked",
            source_span=(0, len(original)), replacement_text=replacement,
        )
        changes = ChangeSet("cs-local", "local:gate", (change,), "c" * 64)
        encryption = EncryptionInfo(
            True, "AES-256-GCM", 1, "gate-key", "local_secret_service"
        )
        current = OptimizationPlan(
            plan_id="plan-local",
            report_id="report-local",
            report_hash="r" * 64,
            profile=OptimizationProfile("agent", 1, "Agent", ("stability",)),
            rule_catalog_version="1",
            recommendations=(),
            selected_ids=(),
            change_set=changes,
            backup_policy=encryption,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        approval = ApprovalRecord(
            "approval-local", current.plan_id, current.report_hash,
            changes.content_hash, "gate", encryption.content_hash,
        )
        rollback = expected is not PlanStatus.COMMITTED
        recovery = expected is PlanStatus.RECOVERY_REQUIRED
        store_type = RestoreFailingStore if recovery else LocalBackupStore
        arguments = (
            (HostCandidate("local:gate", HostKind.LOCAL, "Local Gate"),),
            SubprocessRunner(ProcessPolicy(frozenset())), config, root / "state",
            lambda: GateKeys(),
        )
        if rollback:
            factory = LocalUserApplyTaskFactory(
                *arguments,
                lambda store_root, allowed, cipher: store_type(store_root, allowed, cipher),
                lambda _host, _targets: FailingRuntime(),
            )
        else:
            factory = LocalUserApplyTaskFactory(*arguments)
        started = time.monotonic()
        cpu_started = time.process_time()
        outcome = factory(current, approval)(CancellationToken())
        elapsed = time.monotonic() - started
        cpu = time.process_time() - cpu_started
        assert outcome.status is expected, (expected, outcome.status)
        assert target.read_text(encoding="utf-8") == (
            replacement if expected in (PlanStatus.COMMITTED, PlanStatus.RECOVERY_REQUIRED) else original
        )
        state = root / "state" / "llm-manager"
        backups = tuple((state / "backups").rglob("*.enc"))
        journals = tuple((state / "journal").glob("*.json"))
        assert backups and journals and (state / "audit" / "HEAD").is_file()
        assert state.stat().st_mode & 0o777 == 0o700
        return {
            "status": expected.value,
            "elapsed_ms": round(elapsed * 1000, 3),
            "process_cpu_ms": round(cpu * 1000, 3),
            "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "encrypted_backups": len(backups),
            "journal_records": len(journals),
            "target_state": "replacement" if target.read_text() == replacement else "original",
        }


if __name__ == "__main__":
    statuses = (PlanStatus.COMMITTED, PlanStatus.ROLLED_BACK, PlanStatus.RECOVERY_REQUIRED)
    print(json.dumps({
        "python": platform.python_version(),
        "platform": platform.platform(),
        "scope": "production LocalUserApplyTaskFactory; temporary roots; injected key and failure paths",
        "samples": [sample(status) for status in statuses for _ in range(5)],
    }, indent=2))
