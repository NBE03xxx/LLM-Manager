import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "ssh_cancel_measurement", Path(__file__).parents[1] / "packaging/measure-ssh-cancel.py"
)
measurement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measurement)


class SshCancelMeasurementTests(unittest.TestCase):
    def test_uses_dedicated_noninteractive_trusted_connection(self):
        argv = measurement.ssh_argv("trusted-alias", "read-only-command")
        self.assertEqual(argv[:3], ("ssh", "-S", "none"))
        for option in ("BatchMode=yes", "StrictHostKeyChecking=yes", "UpdateHostKeys=no",
                       "RemoteCommand=none", "RequestTTY=no"):
            self.assertIn(option, argv)
        self.assertEqual(argv[-3:], ("--", "trusted-alias", "read-only-command"))
        self.assertNotIn("-F", argv)

    def test_rejects_unsafe_alias(self):
        for alias in ("-option", "host;command", "host\ncommand"):
            with self.subTest(alias=alias), self.assertRaises(ValueError):
                measurement.ssh_argv(alias, "read-only-command")

    def test_authentication_requirement_stops_before_workload(self):
        with patch.object(measurement.OpenSshHostIdentityResolver, "resolve",
                          return_value=SimpleNamespace(authentication_required=True)), \
                patch.object(measurement.process.SubprocessRunner, "run") as run:
            with self.assertRaisesRegex(ValueError, "noninteractive"):
                measurement.sample("trusted-alias")
            run.assert_not_called()
