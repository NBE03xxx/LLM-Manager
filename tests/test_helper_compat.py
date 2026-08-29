import unittest
from dataclasses import replace

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken, FileStat
from llm_manager.infrastructure.helper_compat import (
    HELPER_PATH,
    METADATA_PATH,
    HelperCompatibilityApplyGate,
    HelperCompatibilityProbe,
    HelperCompatibilityStatus,
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


class _Host:
    def __init__(self, helper, metadata, content):
        self.helper = helper
        self.metadata = metadata
        self.content = content
        self.read_paths = []

    def stat(self, path, cancellation):
        return self.helper if path == HELPER_PATH else self.metadata

    def read_file(self, path, max_bytes, cancellation):
        self.read_paths.append((path, max_bytes))
        return self.content


class _FailingHost:
    def stat(self, path, cancellation):
        raise OSError("injected probe failure")


if __name__ == "__main__":
    unittest.main()
