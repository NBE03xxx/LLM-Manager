from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure.remote_recovery_runtime import RemoteRecoveryRuntime


class RemoteRecoveryRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_uses_absolute_xdg_state_and_private_fixed_attempt_root(self) -> None:
        xdg = self.root / "state"
        runtime = RemoteRecoveryRuntime.for_current_user(
            environ={"XDG_STATE_HOME": str(xdg)}, home=self.root / "home"
        )
        expected = xdg / "llm-manager/remote-recovery"
        self.assertEqual(runtime.state_root, expected)
        self.assertEqual(runtime.attempts.root, expected / "attempts")
        self.assertEqual((xdg / "llm-manager").stat().st_mode & 0o777, 0o700)
        self.assertEqual(expected.stat().st_mode & 0o777, 0o700)

    def test_relative_xdg_falls_back_to_home_state(self) -> None:
        runtime = RemoteRecoveryRuntime.for_current_user(
            environ={"XDG_STATE_HOME": "relative"}, home=self.root / "home"
        )
        self.assertEqual(
            runtime.state_root,
            self.root / "home/.local/state/llm-manager/remote-recovery",
        )

    def test_rejects_unsafe_roots(self) -> None:
        base = self.root / "state"
        base.mkdir()
        application = base / "llm-manager"
        application.mkdir(mode=0o755)
        with self.assertRaisesRegex(AdapterError, "metadata"):
            RemoteRecoveryRuntime.for_current_user(
                environ={"XDG_STATE_HOME": str(base)}, home=self.root / "home"
            )
        application.rmdir()
        target = self.root / "target"
        target.mkdir()
        application.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(AdapterError, "unsafe"):
            RemoteRecoveryRuntime.for_current_user(
                environ={"XDG_STATE_HOME": str(base)}, home=self.root / "home"
            )
        with self.assertRaises(AdapterError):
            RemoteRecoveryRuntime.for_current_user(
                environ={"XDG_STATE_HOME": "/"}, home=self.root / "home"
            )
        with self.assertRaises(AdapterError):
            RemoteRecoveryRuntime.for_current_user(environ={}, home=Path("/"))


if __name__ == "__main__":
    unittest.main()
