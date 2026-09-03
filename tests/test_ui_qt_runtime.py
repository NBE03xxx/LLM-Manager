import os
import threading
import time
import unittest
from dataclasses import replace
from datetime import timedelta

from llm_manager.ui.qt_worker import PYSIDE_AVAILABLE


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 runtime is unavailable")
class QtRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        cls.application = QApplication.instance() or QApplication([])

    def test_thread_pool_keeps_event_loop_responsive_and_emits_result(self) -> None:
        from PySide6.QtCore import QEventLoop, QThread, QTimer

        from llm_manager.ui.qt_worker import QtTaskRunner, QtWorkerCoordinator

        main_thread = QThread.currentThread()
        observed = {"sentinel": False, "result": None, "worker_thread": None}

        def task(_cancellation):
            observed["worker_thread"] = QThread.currentThread()
            time.sleep(0.05)
            return "complete"

        loop = QEventLoop()
        runner = QtTaskRunner(task)
        runner.signals.result.connect(lambda value: observed.__setitem__("result", value))
        runner.signals.finished.connect(loop.quit)
        coordinator = QtWorkerCoordinator()
        coordinator.start("host-1", runner)
        QTimer.singleShot(0, lambda: observed.__setitem__("sentinel", True))
        QTimer.singleShot(2000, loop.quit)
        loop.exec()

        self.assertTrue(observed["sentinel"])
        self.assertEqual(observed["result"], "complete")
        self.assertIsNot(observed["worker_thread"], main_thread)
        self.assertFalse(coordinator.is_active("host-1"))

    def test_cancel_reaches_shared_token_and_emits_cancelled(self) -> None:
        from PySide6.QtCore import QEventLoop, QTimer

        from llm_manager.application.errors import OperationCancelled
        from llm_manager.ui.qt_worker import QtTaskRunner, QtWorkerCoordinator

        started = threading.Event()
        observed = {"cancelled": False}

        def task(cancellation):
            started.set()
            while not cancellation.cancelled:
                time.sleep(0.005)
            raise OperationCancelled("cancelled at safe point")

        loop = QEventLoop()
        runner = QtTaskRunner(task)
        runner.signals.cancelled.connect(lambda: observed.__setitem__("cancelled", True))
        runner.signals.finished.connect(loop.quit)
        coordinator = QtWorkerCoordinator()
        coordinator.start("host-1", runner)

        def cancel_when_started() -> None:
            if started.is_set():
                coordinator.cancel("host-1")
            else:
                QTimer.singleShot(5, cancel_when_started)

        QTimer.singleShot(0, cancel_when_started)
        QTimer.singleShot(2000, loop.quit)
        loop.exec()

        self.assertTrue(observed["cancelled"])
        self.assertFalse(coordinator.is_active("host-1"))

    def test_minimal_window_constructs_and_switches_language(self) -> None:
        from PySide6.QtWidgets import QComboBox, QLabel, QPushButton

        from llm_manager.ui.qt_window import MainWindow

        window = MainWindow(lambda _host_id: lambda _token: None, locale="en")
        try:
            self.assertEqual(window.windowTitle(), "LLM Manager")
            diagnose = window.findChild(QPushButton, "start-diagnosis")
            status = window.findChild(QLabel, "workflow-status")
            language = window.findChild(QComboBox, "language-selector")
            self.assertIsNotNone(diagnose)
            self.assertIsNotNone(status)
            self.assertIsNotNone(language)
            self.assertEqual(diagnose.text(), "Diagnose")
            language.setCurrentIndex(1)
            self.application.processEvents()
            self.assertEqual(diagnose.text(), "診断する")
            self.assertEqual(status.text(), "準備完了")
        finally:
            window.close()

    def test_diagnose_button_runs_worker_and_advances_to_recommendations(self) -> None:
        from PySide6.QtCore import QEventLoop, Qt, QTimer
        from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel, QListWidget, QPushButton

        from llm_manager.application.host_discovery import HostCandidate
        from llm_manager.domain.enums import HostKind
        from llm_manager.domain.enums import PlanStatus
        from llm_manager.domain.models import utc_now
        from llm_manager.infrastructure.safe_apply import ApplyOutcome
        from llm_manager.ui.qt_window import MainWindow
        from tests.test_optimization import diagnostic

        requested = []

        def task_factory(host_id):
            requested.append(host_id)
            source = diagnostic()
            bound_report = replace(source, host=replace(source.host, host_id=host_id))
            return lambda _token: bound_report

        hosts = (
            HostCandidate("local:test", HostKind.LOCAL, "Local"),
            HostCandidate("ssh:development", HostKind.SSH, "development", "development"),
        )
        def change_plan_factory(plan, _report):
            from tests.fixtures import change_set

            return lambda _token: replace(
                plan, change_set=change_set(), expires_at=utc_now() + timedelta(milliseconds=500)
            )

        def apply_task_factory(_plan, _approval):
            return lambda _token: ApplyOutcome(PlanStatus.COMMITTED, None)

        window = MainWindow(
            task_factory,
            locale="en",
            hosts=hosts,
            change_plan_task_factory=change_plan_factory,
            apply_task_factory=apply_task_factory,
        )
        try:
            diagnose = window.findChild(QPushButton, "start-diagnosis")
            navigation = window.findChild(QListWidget, "workflow-navigation")
            status = window.findChild(QLabel, "workflow-status")
            host_selector = window.findChild(QComboBox, "host-selector")
            loop = QEventLoop()

            def finish_when_complete() -> None:
                if navigation.currentRow() == 2:
                    loop.quit()
                else:
                    QTimer.singleShot(5, finish_when_complete)

            host_selector.setCurrentIndex(1)
            diagnose.click()
            QTimer.singleShot(0, finish_when_complete)
            QTimer.singleShot(2000, loop.quit)
            loop.exec()

            self.assertEqual(navigation.currentRow(), 2)
            self.assertEqual(navigation.currentItem().text(), "Recommendations")
            self.assertEqual(status.text(), "Completed")
            self.assertTrue(diagnose.isEnabled())
            self.assertEqual(requested, ["ssh:development"])
            profile_selector = window.findChild(QComboBox, "profile-selector")
            recommendations = window.findChild(QListWidget, "recommendation-list")
            summary = window.findChild(QLabel, "recommendation-summary")
            self.assertEqual(profile_selector.count(), 3)
            self.assertIsNotNone(recommendations)
            self.assertIsNotNone(summary)
            profile_selector.setCurrentIndex(2)
            self.application.processEvents()
            self.assertEqual(recommendations.count(), 2)
            self.assertIn("2 recommendations", summary.text())
            self.assertIn("compaction.", recommendations.item(0).text())
            language = window.findChild(QComboBox, "language-selector")
            language.setCurrentIndex(1)
            self.application.processEvents()
            self.assertEqual(profile_selector.currentText(), "エージェント")
            self.assertIn("推奨 2件", summary.text())
            recommendations.item(0).setCheckState(Qt.CheckState.Checked)
            review_button = window.findChild(QPushButton, "review-selected")
            self.assertTrue(review_button.isEnabled())
            review_button.click()
            review_summary = window.findChild(QLabel, "review-summary")
            review_list = window.findChild(QListWidget, "review-list")

            review_loop = QEventLoop()

            def finish_when_planned() -> None:
                if review_list.count() == 1:
                    review_loop.quit()
                else:
                    QTimer.singleShot(5, finish_when_planned)

            QTimer.singleShot(0, finish_when_planned)
            QTimer.singleShot(2000, review_loop.quit)
            review_loop.exec()
            self.assertEqual(navigation.currentRow(), 3)
            self.assertNotIn("プレビューのみ", review_summary.text())
            self.assertEqual(review_list.count(), 1)
            self.assertIn("-old\n+new", review_list.item(0).text())
            self.assertIn("root権限: 不要", review_list.item(0).text())
            approval = window.findChild(QCheckBox, "approve-change-set")
            approval_status = window.findChild(QLabel, "approval-status")
            plaintext_ack = window.findChild(QCheckBox, "plaintext-backup-ack")
            prepare_apply = window.findChild(QPushButton, "prepare-apply")
            run_apply = window.findChild(QPushButton, "run-sandbox-apply")
            results_summary = window.findChild(QLabel, "results-summary")
            self.assertTrue(approval.isEnabled())
            self.assertFalse(approval.isChecked())
            approval.click()
            self.assertTrue(approval.isChecked())
            self.assertIn("明示承認", approval_status.text())
            self.assertFalse(plaintext_ack.isHidden())
            self.assertFalse(prepare_apply.isEnabled())
            plaintext_ack.click()
            self.assertTrue(prepare_apply.isEnabled())
            prepare_apply.click()
            self.assertEqual(navigation.currentRow(), 4)
            self.assertIn("Applyはまだ開始していません", results_summary.text())
            self.assertTrue(run_apply.isEnabled())
            run_apply.click()

            apply_loop = QEventLoop()

            def finish_when_applied() -> None:
                if "committed" in results_summary.text():
                    apply_loop.quit()
                else:
                    QTimer.singleShot(5, finish_when_applied)

            QTimer.singleShot(0, finish_when_applied)
            QTimer.singleShot(2000, apply_loop.quit)
            apply_loop.exec()
            self.assertIn("committed", results_summary.text())

            stale_loop = QEventLoop()

            def finish_when_stale() -> None:
                if navigation.currentRow() == 3 and not approval.isEnabled():
                    stale_loop.quit()
                else:
                    QTimer.singleShot(5, finish_when_stale)

            QTimer.singleShot(0, finish_when_stale)
            QTimer.singleShot(2000, stale_loop.quit)
            stale_loop.exec()
            self.assertFalse(approval.isEnabled())
            self.assertFalse(approval.isChecked())
            self.assertIn("stale_plan", review_summary.text())
        finally:
            window.close()

    def test_production_availability_keeps_root_route_disabled(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from PySide6.QtWidgets import QLabel, QPushButton

        from llm_manager.application.apply_availability import (
            ApplyRoute,
            AssessProductionApplyAvailability,
        )
        from llm_manager.application.optimization import stable_hash
        from llm_manager.ui.qt_window import MainWindow
        from llm_manager.ui.workflow import GuiPresenter, GuiState, GuiStep, WorkflowStatus
        from tests.fixtures import plan, report

        observed = report()
        template = plan()
        root_change = replace(template.change_set.changes[0], requires_root=True)
        changes = replace(
            template.change_set, host_id=observed.host.host_id, changes=(root_change,)
        )
        current = replace(
            template,
            report_id=observed.report_id,
            report_hash=stable_hash(observed),
            change_set=changes,
        )
        presenter = GuiPresenter()
        apply_factory = MagicMock()
        window = MainWindow(
            lambda _host: lambda _token: observed,
            presenter=presenter,
            apply_task_factory=apply_factory,
            apply_availability_service=AssessProductionApplyAvailability(
                frozenset({ApplyRoute.LOCAL_USER})
            ),
        )
        try:
            presenter._state = GuiState(
                step=GuiStep.RESULTS,
                status=WorkflowStatus.SUCCESS,
                selected_host_id=observed.host.host_id,
                report=observed,
                approval_id="approval-test",
            )
            window._recommendation_plan = current
            window._approval_record = SimpleNamespace(approval_id="approval-test")
            window._render_results()
            run_apply = window.findChild(QPushButton, "run-sandbox-apply")
            summary = window.findChild(QLabel, "results-summary")
            self.assertFalse(run_apply.isEnabled())
            self.assertIn("local root", summary.text())
            window._run_apply()
            apply_factory.assert_not_called()
            user_change = replace(root_change, requires_root=False)
            window._recommendation_plan = replace(
                current, change_set=replace(changes, changes=(user_change,))
            )
            window._render_results()
            self.assertTrue(run_apply.isEnabled())
        finally:
            window.close()

    def test_results_runs_local_user_composition_in_temporary_roots(self) -> None:
        import hashlib
        import tempfile
        from pathlib import Path

        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QLabel, QPushButton

        from llm_manager.application.apply_availability import (
            ApplyRoute,
            AssessProductionApplyAvailability,
        )
        from llm_manager.application.host_discovery import HostCandidate
        from llm_manager.application.optimization import stable_hash
        from llm_manager.domain.enums import ChangeOperation, HostKind, PlanStatus
        from llm_manager.domain.models import ApprovalRecord, Change, ChangeSet, EncryptionInfo
        from llm_manager.infrastructure.process import ProcessPolicy, SubprocessRunner
        from llm_manager.ui.composition import LocalUserApplyTaskFactory
        from llm_manager.ui.qt_window import MainWindow
        from llm_manager.ui.workflow import GuiPresenter, GuiState, GuiStep, WorkflowStatus
        from tests.fixtures import plan, report

        class TestKeys:
            def get_key(self, _reference: str, _scope: str) -> bytes:
                return b"k" * 32

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            target_root = config / "opencode"
            target_root.mkdir(parents=True)
            target = target_root / "opencode.json"
            original = '{"model":"old"}'
            replacement = '{"model":"new"}'
            target.write_text(original, encoding="utf-8")
            observed = report()
            change = Change(
                "change-local", str(target), ChangeOperation.REPLACE_FILE,
                "old", "new", hashlib.sha256(original.encode()).hexdigest(), "masked",
                source_span=(0, len(original)), replacement_text=replacement,
            )
            changes = ChangeSet(
                "cs-local", observed.host.host_id, (change,), "c" * 64
            )
            encryption = EncryptionInfo(
                True, "AES-256-GCM", 1, "local-master-v1", "local_secret_service"
            )
            current = replace(
                plan(), report_id=observed.report_id, report_hash=stable_hash(observed),
                change_set=changes, backup_policy=encryption,
            )
            approval = ApprovalRecord(
                "approval-local", current.plan_id, current.report_hash,
                changes.content_hash, "tester", encryption.content_hash,
            )
            presenter = GuiPresenter()
            apply_factory = LocalUserApplyTaskFactory(
                (HostCandidate(observed.host.host_id, HostKind.LOCAL, "Local"),),
                SubprocessRunner(ProcessPolicy(frozenset())), config, root / "state",
                lambda: TestKeys(),
            )
            window = MainWindow(
                lambda _host: lambda _token: observed,
                presenter=presenter,
                apply_task_factory=apply_factory,
                apply_availability_service=AssessProductionApplyAvailability(
                    frozenset({ApplyRoute.LOCAL_USER})
                ),
            )
            try:
                presenter._state = GuiState(
                    step=GuiStep.RESULTS,
                    status=WorkflowStatus.SUCCESS,
                    selected_host_id=observed.host.host_id,
                    report=observed,
                    plan_hash=changes.content_hash,
                    approved_plan_hash=changes.content_hash,
                    approval_id=approval.approval_id,
                )
                window._recommendation_plan = current
                window._approval_record = approval
                window._render()
                run_apply = window.findChild(QPushButton, "run-sandbox-apply")
                summary = window.findChild(QLabel, "results-summary")
                self.assertTrue(run_apply.isEnabled())
                run_apply.click()
                loop = QEventLoop()

                def finish_when_applied() -> None:
                    if "committed" in summary.text():
                        loop.quit()
                    else:
                        QTimer.singleShot(5, finish_when_applied)

                QTimer.singleShot(0, finish_when_applied)
                QTimer.singleShot(2000, loop.quit)
                loop.exec()
                self.assertIn("committed", summary.text())
                self.assertEqual(target.read_text(encoding="utf-8"), replacement)
                state = root / "state" / "llm-manager"
                self.assertTrue(any((state / "backups").rglob("*.enc")))
                self.assertTrue((state / "audit" / "HEAD").is_file())
                self.assertTrue(any((state / "journal").glob("*.json")))
            finally:
                window.close()

    def test_results_shows_rollback_and_recovery_required_from_local_composition(self) -> None:
        import hashlib
        import tempfile
        from pathlib import Path

        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QLabel, QPushButton

        from llm_manager.application.apply_availability import ApplyRoute, AssessProductionApplyAvailability
        from llm_manager.application.errors import AdapterError
        from llm_manager.application.host_discovery import HostCandidate
        from llm_manager.application.optimization import stable_hash
        from llm_manager.domain.enums import ChangeOperation, HostKind, PlanStatus, Severity, ValidationStatus
        from llm_manager.domain.models import ApprovalRecord, Change, ChangeSet, EncryptionInfo, LocalizedMessage, ValidationResult
        from llm_manager.infrastructure.backup import LocalBackupStore
        from llm_manager.infrastructure.process import ProcessPolicy, SubprocessRunner
        from llm_manager.ui.composition import LocalUserApplyTaskFactory
        from llm_manager.ui.qt_window import MainWindow
        from llm_manager.ui.workflow import GuiPresenter, GuiState, GuiStep, WorkflowStatus
        from tests.fixtures import plan, report

        class TestKeys:
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

        def run_case(restore_fails: bool) -> tuple[str, str]:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = root / "config"
                target_root = config / "opencode"
                target_root.mkdir(parents=True)
                target = target_root / "opencode.json"
                original = '{"model":"old"}'
                target.write_text(original, encoding="utf-8")
                observed = report()
                change = Change(
                    "change-local", str(target), ChangeOperation.REPLACE_FILE,
                    "old", "new", hashlib.sha256(original.encode()).hexdigest(), "masked",
                    source_span=(0, len(original)), replacement_text='{"model":"new"}',
                )
                changes = ChangeSet("cs-local", observed.host.host_id, (change,), "c" * 64)
                encryption = EncryptionInfo(
                    True, "AES-256-GCM", 1, "local-master-v1", "local_secret_service"
                )
                current = replace(
                    plan(), report_id=observed.report_id,
                    report_hash=stable_hash(observed), change_set=changes,
                    backup_policy=encryption,
                )
                approval = ApprovalRecord(
                    "approval-local", current.plan_id, current.report_hash,
                    changes.content_hash, "tester", encryption.content_hash,
                )
                store_type = RestoreFailingStore if restore_fails else LocalBackupStore
                apply_factory = LocalUserApplyTaskFactory(
                    (HostCandidate(observed.host.host_id, HostKind.LOCAL, "Local"),),
                    SubprocessRunner(ProcessPolicy(frozenset())), config, root / "state",
                    lambda: TestKeys(),
                    lambda store_root, allowed, cipher: store_type(store_root, allowed, cipher),
                    lambda _host, _candidates: FailingRuntime(),
                )
                presenter = GuiPresenter()
                window = MainWindow(
                    lambda _host: lambda _token: observed,
                    presenter=presenter,
                    apply_task_factory=apply_factory,
                    apply_availability_service=AssessProductionApplyAvailability(
                        frozenset({ApplyRoute.LOCAL_USER})
                    ),
                )
                try:
                    presenter._state = GuiState(
                        step=GuiStep.RESULTS, status=WorkflowStatus.SUCCESS,
                        selected_host_id=observed.host.host_id, report=observed,
                        plan_hash=changes.content_hash,
                        approved_plan_hash=changes.content_hash,
                        approval_id=approval.approval_id,
                    )
                    window._recommendation_plan = current
                    window._approval_record = approval
                    window._render()
                    window.findChild(QPushButton, "run-sandbox-apply").click()
                    summary = window.findChild(QLabel, "results-summary")
                    expected = "recovery_required" if restore_fails else "rolled_back"
                    loop = QEventLoop()

                    def finish() -> None:
                        if expected in summary.text():
                            loop.quit()
                        else:
                            QTimer.singleShot(5, finish)

                    QTimer.singleShot(0, finish)
                    QTimer.singleShot(2000, loop.quit)
                    loop.exec()
                    return summary.text(), target.read_text(encoding="utf-8")
                finally:
                    window.close()

        rolled_back_summary, rolled_back_content = run_case(False)
        self.assertIn(PlanStatus.ROLLED_BACK.value, rolled_back_summary)
        self.assertEqual(rolled_back_content, '{"model":"old"}')
        recovery_summary, recovery_content = run_case(True)
        self.assertIn(PlanStatus.RECOVERY_REQUIRED.value, recovery_summary)
        self.assertEqual(recovery_content, '{"model":"new"}')

    def test_backup_inventory_refresh_is_read_only_and_localized(self) -> None:
        from types import SimpleNamespace

        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QComboBox, QLabel, QListWidget, QPushButton

        from llm_manager.ui.qt_window import MainWindow

        calls = []
        item = SimpleNamespace(
            backup_id="backup-1",
            state=SimpleNamespace(value="local_only"),
            local_presence=SimpleNamespace(value="present"),
            remote_presence=SimpleNamespace(value="absent"),
            protected=True,
            requires_attention=True,
            allowed_actions=(SimpleNamespace(value="refresh_inventory"),),
        )

        def inventory_factory(host_id):
            calls.append(("factory", host_id))

            def load(_cancellation):
                calls.append(("load", host_id))
                return (item,)

            return load

        window = MainWindow(
            lambda _host: lambda _token: None,
            locale="en",
            backup_inventory_task_factory=inventory_factory,
        )
        try:
            refresh = window.findChild(QPushButton, "refresh-backup-inventory")
            summary = window.findChild(QLabel, "backup-inventory-summary")
            inventory = window.findChild(QListWidget, "backup-inventory-list")
            self.assertEqual(calls, [])
            self.assertEqual(inventory.count(), 0)
            refresh.click()
            loop = QEventLoop()

            def finish() -> None:
                if inventory.count() == 1:
                    loop.quit()
                else:
                    QTimer.singleShot(5, finish)

            QTimer.singleShot(0, finish)
            QTimer.singleShot(2000, loop.quit)
            loop.exec()
            self.assertEqual(calls, [("factory", "local"), ("load", "local")])
            self.assertIn("read-only", summary.text())
            self.assertIn("backup-1 · local_only", inventory.item(0).text())
            self.assertIn("actions: refresh_inventory", inventory.item(0).text())
            language = window.findChild(QComboBox, "language-selector")
            language.setCurrentIndex(1)
            self.application.processEvents()
            self.assertIn("read-only", summary.text())
            self.assertIn("要確認: true", inventory.item(0).text())
            self.assertEqual(len(calls), 2)
        finally:
            window.close()

    def test_restore_preview_requires_exact_approval_and_refresh_invalidates_it(self) -> None:
        from types import SimpleNamespace

        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QCheckBox, QLabel, QListWidget, QPushButton

        from llm_manager.application.restore_preview import CreateRestorePreview
        from llm_manager.domain.models import BackupItem, BackupManifest, EncryptionInfo, utc_now
        from llm_manager.ui.qt_window import MainWindow

        now = utc_now()
        manifest = BackupManifest(
            backup_id="backup-1", schema_version="1.0", plan_id="plan-1",
            change_set_hash="c" * 64, host_id="local", host_fingerprint=None,
            items=(BackupItem(
                target="/tmp/config.json", existed=True, content_ref="item-0.bin",
                sha256="a" * 64, mode=0o600,
            ),),
            manifest_hash="b" * 64, storage_location="/tmp/metadata-only",
            encryption=EncryptionInfo(enabled=False), protected=False,
            created_at=now, retention_expires_at=now + timedelta(days=30),
            complete=True,
        )
        preview = CreateRestorePreview().execute(manifest)
        inventory_item = SimpleNamespace(
            backup_id="backup-1", state="committed",
            local_presence="present", remote_presence="absent",
            protected=False, requires_attention=False, allowed_actions=(),
        )

        def inventory_factory(_host_id):
            return lambda _token: (inventory_item,)

        def preview_factory(host_id, backup_id):
            self.assertEqual((host_id, backup_id), ("local", "backup-1"))
            return lambda _token: preview

        window = MainWindow(
            lambda _host: lambda _token: None,
            backup_inventory_task_factory=inventory_factory,
            restore_preview_task_factory=preview_factory,
        )
        try:
            refresh = window.findChild(QPushButton, "refresh-backup-inventory")
            inventory = window.findChild(QListWidget, "backup-inventory-list")
            preview_list = window.findChild(QListWidget, "restore-preview-list")
            approval = window.findChild(QCheckBox, "approve-restore-preview")
            status = window.findChild(QLabel, "restore-approval-status")
            refresh.click()
            loop = QEventLoop()

            def select_when_loaded() -> None:
                if inventory.count() == 1:
                    inventory.setCurrentRow(0)
                if preview_list.count() == 1:
                    loop.quit()
                else:
                    QTimer.singleShot(5, select_when_loaded)

            QTimer.singleShot(0, select_when_loaded)
            QTimer.singleShot(2000, loop.quit)
            loop.exec()
            self.assertIn("/tmp/config.json", preview_list.item(0).text())
            self.assertNotIn("old", preview_list.item(0).text())
            self.assertTrue(approval.isEnabled())
            approval.click()
            self.assertTrue(approval.isChecked())
            self.assertIn("exact preview", status.text())
            refresh.click()
            self.application.processEvents()
            self.assertFalse(approval.isChecked())
            self.assertFalse(approval.isEnabled())
        finally:
            window.close()

    def test_restore_preview_expiry_clears_approval_without_mutation(self) -> None:
        from types import SimpleNamespace

        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QCheckBox, QLabel, QListWidget, QPushButton

        from llm_manager.application.restore_preview import RestorePreview, RestorePreviewItem
        from llm_manager.domain.models import utc_now
        from llm_manager.ui.qt_window import MainWindow

        now = utc_now()
        preview = RestorePreview(
            "local", "backup-expiring", "a" * 64, now,
            now + timedelta(milliseconds=150), False,
            (RestorePreviewItem("/tmp/config.json", True, "b" * 64, 0o600),),
        ).with_hash()
        item = SimpleNamespace(
            backup_id="backup-expiring", state="committed",
            local_presence="present", remote_presence="absent",
            protected=False, requires_attention=False, allowed_actions=(),
        )
        window = MainWindow(
            lambda _host: lambda _token: None,
            backup_inventory_task_factory=lambda _host: lambda _token: (item,),
            restore_preview_task_factory=(
                lambda _host, _backup: lambda _token: preview
            ),
        )
        try:
            refresh = window.findChild(QPushButton, "refresh-backup-inventory")
            inventory = window.findChild(QListWidget, "backup-inventory-list")
            approval = window.findChild(QCheckBox, "approve-restore-preview")
            summary = window.findChild(QLabel, "restore-preview-summary")
            refresh.click()
            ready = QEventLoop()

            def approve_when_ready() -> None:
                if inventory.count() == 1 and inventory.currentRow() < 0:
                    inventory.setCurrentRow(0)
                if approval.isEnabled():
                    approval.click()
                    ready.quit()
                else:
                    QTimer.singleShot(5, approve_when_ready)

            QTimer.singleShot(0, approve_when_ready)
            QTimer.singleShot(2000, ready.quit)
            ready.exec()
            self.assertTrue(approval.isChecked())

            expired = QEventLoop()

            def finish_when_expired() -> None:
                if not approval.isEnabled() and "stale_restore_preview" in summary.text():
                    expired.quit()
                else:
                    QTimer.singleShot(5, finish_when_expired)

            QTimer.singleShot(0, finish_when_expired)
            QTimer.singleShot(2000, expired.quit)
            expired.exec()
            self.assertFalse(approval.isChecked())
            self.assertFalse(approval.isEnabled())
            self.assertIn("stale_restore_preview", summary.text())
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
