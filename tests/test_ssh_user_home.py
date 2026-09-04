from __future__ import annotations

import unittest

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken, CommandResult
from llm_manager.infrastructure.ssh_user_home import ResolveSshUserHome


class ResolveSshUserHomeTests(unittest.TestCase):
    def test_uses_fixed_uid_and_passwd_commands_and_returns_three_candidates(self) -> None:
        host = _Host("1000\n", "alice:x:1000:1000:Alice:/home/alice:/bin/bash\n")
        result = ResolveSshUserHome().execute(host, CancellationToken())
        self.assertEqual(result.uid, 1000)
        self.assertEqual(result.username, "alice")
        self.assertEqual(
            result.opencode_candidates,
            (
                "/home/alice/.config/opencode/opencode.jsonc",
                "/home/alice/.config/opencode/opencode.json",
                "/home/alice/.config/opencode/config.json",
            ),
        )
        self.assertEqual(host.argv, [("id", "-u"), ("getent", "passwd", "1000")])

    def test_maps_only_exact_candidates_to_fixed_home_relative_targets(self) -> None:
        home = ResolveSshUserHome().execute(
            _Host("1000\n", "alice:x:1000:1000::/home/alice:/bin/sh\n"),
            CancellationToken(),
        )
        target = "/home/alice/.config/opencode/opencode.jsonc"
        self.assertEqual(
            home.helper_target_map((target,)),
            {target: ".config/opencode/opencode.jsonc"},
        )
        for targets in (
            (),
            (target, target),
            ("/home/alice/.config/opencode/opencode.jsonc.backup",),
            ("/home/alice-other/.config/opencode/opencode.jsonc",),
        ):
            with self.subTest(targets=targets), self.assertRaises(AdapterError) as caught:
                home.helper_target_map(targets)
            self.assertEqual(caught.exception.code, "ssh_user_config_not_allowed")

    def test_rejects_root_relative_ambiguous_and_uid_mismatch(self) -> None:
        cases = (
            ("0\n", "root:x:0:0:root:/root:/bin/bash", "ssh_user_identity_invalid"),
            ("1000\n", "alice:x:1000:1000::relative:/bin/bash", "ssh_user_home_invalid"),
            ("1000\n", "a:x:1000:1000::/home/a:/bin/sh\nb:x:1000:1000::/home/b:/bin/sh", "ssh_user_home_invalid"),
            ("1000\n", "alice:x:1001:1001::/home/alice:/bin/bash", "ssh_user_home_invalid"),
        )
        for uid, passwd, code in cases:
            with self.subTest(passwd=passwd), self.assertRaises(AdapterError) as caught:
                ResolveSshUserHome().execute(_Host(uid, passwd), CancellationToken())
            self.assertEqual(caught.exception.code, code)

    def test_failure_timeout_and_cancellation_fail_closed(self) -> None:
        with self.assertRaises(AdapterError):
            ResolveSshUserHome().execute(_Host("", "", uid_exit=1), CancellationToken())
        with self.assertRaises(AdapterError):
            ResolveSshUserHome().execute(_Host("1000", "", passwd_timeout=True), CancellationToken())
        with self.assertRaisesRegex(Exception, "cancelled"):
            ResolveSshUserHome().execute(_Host("1000", ""), CancellationToken(True))


class _Host:
    def __init__(self, uid, passwd, *, uid_exit=0, passwd_timeout=False):
        self.uid, self.passwd = uid, passwd
        self.uid_exit, self.passwd_timeout = uid_exit, passwd_timeout
        self.argv = []

    def execute_readonly(self, request, cancellation):
        self.argv.append(request.argv)
        if request.argv == ("id", "-u"):
            return CommandResult(request.argv, self.uid_exit, self.uid, "", False, 1)
        return CommandResult(request.argv, None if self.passwd_timeout else 0, self.passwd, "", self.passwd_timeout, 1)


if __name__ == "__main__":
    unittest.main()
