from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken, HostPort

from .helper_protocol import PROTOCOL_VERSION

HELPER_PATH = "/usr/bin/llm-manager-helper"
METADATA_PATH = "/usr/share/llm-manager/helper-metadata.json"
MAX_METADATA_BYTES = 4096


class HelperCompatibilityStatus(StrEnum):
    READY = "ready"
    MISSING = "missing"
    UNSAFE = "unsafe"
    INVALID = "invalid"
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True, slots=True)
class HelperCompatibility:
    status: HelperCompatibilityStatus
    package: str | None = None
    package_version: str | None = None
    protocol_version: int | None = None
    reason: str | None = None

    @property
    def root_apply_allowed(self) -> bool:
        return self.status is HelperCompatibilityStatus.READY


class HelperCompatibilityProbe:
    """Read-only verification of an installed local or remote helper package."""

    def __init__(self, expected_package: str, compatible_versions: frozenset[str]) -> None:
        if not expected_package or not compatible_versions:
            raise ValueError("helper package and compatible versions are required")
        self.expected_package = expected_package
        self.compatible_versions = compatible_versions

    def inspect(self, host: HostPort, cancellation: CancellationToken) -> HelperCompatibility:
        helper = host.stat(HELPER_PATH, cancellation)
        metadata = host.stat(METADATA_PATH, cancellation)
        if not helper.exists or not metadata.exists:
            return HelperCompatibility(HelperCompatibilityStatus.MISSING, reason="helper_not_installed")
        if (
            helper.path != HELPER_PATH
            or metadata.path != METADATA_PATH
            or helper.is_symlink
            or metadata.is_symlink
            or helper.uid != 0
            or metadata.uid != 0
            or helper.gid != 0
            or metadata.gid != 0
            or helper.mode != 0o755
            or metadata.mode != 0o644
        ):
            return HelperCompatibility(HelperCompatibilityStatus.UNSAFE, reason="unsafe_helper_metadata")
        try:
            content = host.read_file(METADATA_PATH, MAX_METADATA_BYTES, cancellation)
            value = json.loads(content.decode("utf-8"))
            if not isinstance(value, dict) or set(value) != {
                "package", "package_version", "protocol_version", "schema_version"
            }:
                raise ValueError("invalid metadata fields")
            package = _text(value, "package")
            package_version = _text(value, "package_version")
            protocol_version = value["protocol_version"]
            if value["schema_version"] != "1.0" or type(protocol_version) is not int:
                raise ValueError("unsupported metadata schema")
            canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
            if canonical != content:
                raise ValueError("metadata is not canonical")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, KeyError):
            return HelperCompatibility(HelperCompatibilityStatus.INVALID, reason="invalid_helper_metadata")
        result = HelperCompatibility(
            HelperCompatibilityStatus.READY,
            package,
            package_version,
            protocol_version,
        )
        if (
            package != self.expected_package
            or package_version not in self.compatible_versions
            or protocol_version != PROTOCOL_VERSION
        ):
            return HelperCompatibility(
                HelperCompatibilityStatus.INCOMPATIBLE,
                package,
                package_version,
                protocol_version,
                "incompatible_helper",
            )
        return result

    def root_apply_allowed(self, host: HostPort, cancellation: CancellationToken) -> bool:
        return self.inspect(host, cancellation).root_apply_allowed


@dataclass(frozen=True, slots=True)
class HelperCompatibilityApplyGate:
    """Revalidate the installed helper immediately before privileged execution."""

    host: HostPort
    probe: HelperCompatibilityProbe

    def assert_ready(self, cancellation: CancellationToken) -> None:
        try:
            result = self.probe.inspect(self.host, cancellation)
        except (OSError, ValueError) as error:
            raise AdapterError(
                "privileged_helper_unavailable", "helper compatibility probe failed"
            ) from error
        if not result.root_apply_allowed:
            raise AdapterError(
                "privileged_helper_unavailable",
                result.reason or result.status.value,
            )


def _text(value: dict[str, object], key: str) -> str:
    item = value[key]
    if not isinstance(item, str) or not item:
        raise ValueError(f"invalid {key}")
    return item
