"""Phase 6 complete local production diagnosis baseline.

Run from a source checkout with PYTHONPATH=src on a supported environment that
already has a reachable Ollama API and OpenCode binary. This script is read-only.
"""
from __future__ import annotations

import json
import platform
import resource
import time

from llm_manager.application.host_discovery import HostCandidate
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.enums import HostKind, ProbeStatus, ReportStatus
from llm_manager.ui.composition import DiagnosticTaskFactory


def main() -> None:
    host = HostCandidate("local:complete-gate", HostKind.LOCAL, "Local Complete Gate")
    factory = DiagnosticTaskFactory.production((host,))
    samples = []
    for _ in range(5):
        started = time.monotonic()
        cpu_started = time.process_time()
        report = factory(host.host_id)(CancellationToken())
        elapsed = time.monotonic() - started
        cpu = time.process_time() - cpu_started
        assert report.status is ReportStatus.COMPLETE
        assert report.system is not None and report.hardware is not None
        assert report.ollama is not None
        assert report.ollama.api_connectivity is ProbeStatus.OK
        assert report.ollama.version is not None
        assert report.opencode is not None and report.opencode.installed
        assert report.opencode.version is not None
        samples.append({
            "status": report.status.value,
            "elapsed_ms": round(elapsed * 1000, 3),
            "process_cpu_ms": round(cpu * 1000, 3),
            "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "ollama_version": report.ollama.version,
            "ollama_connectivity": report.ollama.api_connectivity.value,
            "opencode_version": report.opencode.version,
            "opencode_binary": report.opencode.binary_path,
            "system_observed": report.system.distribution != "",
            "hardware_observed": report.hardware.logical_cores > 0,
            "can_elevate": report.host.capabilities.can_elevate,
        })
    print(json.dumps({
        "python": platform.python_version(),
        "platform": platform.platform(),
        "scope": "production DiagnosticTaskFactory; live read-only Ollama and installed OpenCode",
        "samples": samples,
    }, indent=2))


if __name__ == "__main__":
    main()
