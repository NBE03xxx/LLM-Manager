from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure.backup_evidence_runtime import (
    BackupEvidenceRetentionRuntime,
)


class BackupEvidenceRetentionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_uses_absolute_xdg_state_and_prepares_private_roots(self):
        xdg = self.root / "state"
        runtime = BackupEvidenceRetentionRuntime.for_current_user(
            environ={"XDG_STATE_HOME": str(xdg)}, home=self.root / "home"
        )
        expected = xdg / "llm-manager/backup-evidence-retention"
        self.assertEqual(runtime.state_root, expected)
        self.assertEqual(runtime.executions.root, expected / "executions")
        self.assertEqual(
            runtime.cleanup_requests.root, expected / "cleanup-requests"
        )
        self.assertEqual((xdg / "llm-manager").stat().st_mode & 0o777, 0o700)
        self.assertEqual(expected.stat().st_mode & 0o777, 0o700)

    def test_relative_xdg_falls_back_to_home_state(self):
        runtime = BackupEvidenceRetentionRuntime.for_current_user(
            environ={"XDG_STATE_HOME": "relative/state"}, home=self.root / "home"
        )
        self.assertEqual(
            runtime.state_root,
            self.root / "home/.local/state/llm-manager/backup-evidence-retention",
        )

    def test_rejects_unsafe_existing_application_root(self):
        base = self.root / "state"
        base.mkdir()
        application = base / "llm-manager"
        application.mkdir(mode=0o755)
        with self.assertRaisesRegex(AdapterError, "metadata"):
            BackupEvidenceRetentionRuntime.for_current_user(
                environ={"XDG_STATE_HOME": str(base)}, home=self.root / "home"
            )
        application.rmdir()
        target = self.root / "target"
        target.mkdir()
        application.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(AdapterError, "unsafe"):
            BackupEvidenceRetentionRuntime.for_current_user(
                environ={"XDG_STATE_HOME": str(base)}, home=self.root / "home"
            )

    def test_rejects_root_state_and_home(self):
        with self.assertRaises(AdapterError):
            BackupEvidenceRetentionRuntime.for_current_user(
                environ={"XDG_STATE_HOME": "/"}, home=self.root / "home"
            )
        with self.assertRaises(AdapterError):
            BackupEvidenceRetentionRuntime.for_current_user(environ={}, home=Path("/"))
