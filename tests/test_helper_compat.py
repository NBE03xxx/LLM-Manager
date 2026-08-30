import hashlib
import unittest
from dataclasses import replace

from llm_manager.adapters.host.openssh import OpenSshHostAdapter
from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken, CommandResult, FileStat
from llm_manager.infrastructure.helper_compat import (
    HELPER_PATH,
    METADATA_PATH,
    HelperCompatibilityApplyGate,
    HelperCompatibilityProbe,
    HelperCompatibilityStatus,
    REMOTE_HELPER_PATH,
    REMOTE_METADATA_PATH,
    remote_helper_compatibility_probe,
)


METADATA = b'{"package":"llm-manager","package_version":"0.1.0~dev0","protocol_version":1,"schema_version":"1.0"}\n'


class HelperCompatibilityProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.probe = HelperCompatibilityProbe("llm-manager", frozenset({"0.1.0~dev0"}))
        self.host = _Host(
            FileStat(HELPER_PATH, True, mode=0o755, uid=0, gid=0),
            FileStat(METADATA_PATH, True, mode=0o644, uid=0, gid=0),
            METADATA,
        )

    def test_accepts_only_matching_root_owned_package_and_protocol(self) -> None:
        result = self.probe.inspect(self.host, CancellationToken())
        self.assertEqual(result.status, HelperCompatibilityStatus.READY)
        self.assertTrue(result.root_apply_allowed)
        self.assertEqual(self.host.read_paths, [(METADATA_PATH, 4096)])

    def test_missing_or_unsafe_helper_is_read_only(self) -> None:
        missing = _Host(replace(self.host.helper, exists=False), self.host.metadata, METADATA)
        self.assertEqual(
            self.probe.inspect(missing, CancellationToken()).status,
            HelperCompatibilityStatus.MISSING,
        )
        unsafe_cases = (
            replace(self.host.helper, uid=1000),
            replace(self.host.helper, mode=0o775),
            replace(self.host.helper, is_symlink=True),
        )
        for helper in unsafe_cases:
            with self.subTest(helper=helper):
                result = self.probe.inspect(
                    _Host(helper, self.host.metadata, METADATA), CancellationToken()
                )
                self.assertEqual(result.status, HelperCompatibilityStatus.UNSAFE)
                self.assertFalse(result.root_apply_allowed)

    def test_rejects_noncanonical_invalid_and_incompatible_metadata(self) -> None:
        invalid_values = (
            METADATA.rstrip(b"\n"),
            METADATA.replace(b'"protocol_version":1', b'"protocol_version":"1"'),
            METADATA.replace(b'"schema_version":"1.0"', b'"unknown":true'),
        )
        for content in invalid_values:
            with self.subTest(content=content):
                result = self.probe.inspect(
                    _Host(self.host.helper, self.host.metadata, content), CancellationToken()
                )
                self.assertEqual(result.status, HelperCompatibilityStatus.INVALID)

        for content in (
            METADATA.replace(b'"llm-manager"', b'"other-helper"'),
            METADATA.replace(b'"0.1.0~dev0"', b'"0.2.0"'),
            METADATA.replace(b'"protocol_version":1', b'"protocol_version":2'),
        ):
            with self.subTest(content=content):
                result = self.probe.inspect(
                    _Host(self.host.helper, self.host.metadata, content), CancellationToken()
                )
                self.assertEqual(result.status, HelperCompatibilityStatus.INCOMPATIBLE)
                self.assertFalse(result.root_apply_allowed)

    def test_apply_gate_rechecks_and_fails_closed(self) -> None:
        HelperCompatibilityApplyGate(self.host, self.probe).assert_ready(CancellationToken())
        missing = _Host(replace(self.host.helper, exists=False), self.host.metadata, METADATA)
        for host in (missing, _FailingHost()):
            with self.subTest(host=host), self.assertRaises(AdapterError) as caught:
                HelperCompatibilityApplyGate(host, self.probe).assert_ready(CancellationToken())
            self.assertEqual(caught.exception.code, "privileged_helper_unavailable")

    def test_remote_probe_uses_separate_paths_package_and_content_hashes(self) -> None:
        metadata = b'{"package":"llm-manager-remote-helper","package_version":"0.1.0~dev0","protocol_version":1,"schema_version":"1.0"}\n'
        host = _Host(
            FileStat(
                REMOTE_HELPER_PATH, True, sha256="a" * 64, mode=0o755, uid=0, gid=0
            ),
            FileStat(
                REMOTE_METADATA_PATH,
                True,
                sha256=hashlib.sha256(metadata).hexdigest(),
                mode=0o644,
                uid=0,
                gid=0,
            ),
            metadata,
        )
        probe = remote_helper_compatibility_probe(frozenset({"0.1.0~dev0"}))
        self.assertEqual(
            probe.inspect(host, CancellationToken()).status,
            HelperCompatibilityStatus.READY,
        )
        changed = _Host(host.helper, host.metadata, metadata.replace(b"dev0", b"dev1"))
        self.assertEqual(
            probe.inspect(changed, CancellationToken()).status,
            HelperCompatibilityStatus.INVALID,
        )

    def test_remote_probe_crosses_openssh_readonly_boundary(self) -> None:
        runner = _RemoteProbeRunner()
        host = OpenSshHostAdapter(
            "development", runner, control_socket="/tmp/llm-manager-cm"
        )
        probe = remote_helper_compatibility_probe(frozenset({"0.1.0~dev0"}))
        result = probe.inspect(host, CancellationToken())
        self.assertEqual(result.status, HelperCompatibilityStatus.READY)
        self.assertEqual(len(runner.requests), 5)
        self.assertTrue(
            all(
                request.argv[:3] == ("ssh", "-S", "/tmp/llm-manager-cm")
                for request in runner.requests
            )
        )
        self.assertTrue(all("BatchMode=yes" in request.argv for request in runner.requests))

    def test_remote_missing_helper_stops_after_stat_without_read(self) -> None:
        runner = _RemoteProbeRunner(missing=True)
        host = OpenSshHostAdapter("development", runner)
        result = remote_helper_compatibility_probe(
            frozenset({"0.1.0~dev0"})
        ).inspect(host, CancellationToken())
        self.assertEqual(result.status, HelperCompatibilityStatus.MISSING)
        self.assertEqual(result.reason, "helper_not_installed")
        self.assertEqual(len(runner.requests), 2)
        self.assertTrue(all(" stat " in request.argv[-1] for request in runner.requests))


class _Host:
    def __init__(self, helper, metadata, content):
        self.helper = helper
        self.metadata = metadata
        self.content = content
        self.read_paths = []

    def stat(self, path, cancellation):
        return self.helper if path == self.helper.path else self.metadata

    def read_file(self, path, max_bytes, cancellation):
        self.read_paths.append((path, max_bytes))
        return self.content


class _FailingHost:
    def stat(self, path, cancellation):
        raise OSError("injected probe failure")


class _RemoteProbeRunner:
    def __init__(self, *, missing=False):
        self.requests = []
        self.missing = missing
        self.metadata = b'{"package":"llm-manager-remote-helper","package_version":"0.1.0~dev0","protocol_version":1,"schema_version":"1.0"}\n'

    def run(self, request, cancellation):
        self.requests.append(request)
        remote = request.argv[-1]
        if " stat " in remote:
            if self.missing:
                return CommandResult(request.argv, 1, "", "missing", False, 1)
            mode = "755" if REMOTE_HELPER_PATH in remote else "644"
            size = 6 if REMOTE_HELPER_PATH in remote else len(self.metadata)
            output = f"regular file|{mode}|0|0|{size}"
        elif REMOTE_HELPER_PATH in remote:
            output = "helper"
        else:
            output = self.metadata.decode("utf-8")
        return CommandResult(request.argv, 0, output, "", False, 1)


if __name__ == "__main__":
    unittest.main()
