"""Read-only SSH diagnosis baseline; no interactive authentication or target writes.

Run with PYTHONPATH=src and a trusted system OpenSSH alias. Partial reports are
reported as partial, not rejected or counted as complete diagnosis evidence.
"""
from __future__ import annotations

import argparse
import json
import platform
import resource
import statistics
import time

from llm_manager.application.host_discovery import HostCandidate
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.enums import HostKind, ProbeStatus
from llm_manager.infrastructure.ssh_auth import SshAliasAuthRequest
from llm_manager.ui.composition import DiagnosticTaskFactory


def measure(alias: str, samples: int = 5) -> dict[str, object]:
    SshAliasAuthRequest(alias)
    if not 1 <= samples <= 20:
        raise ValueError("samples must be between 1 and 20")
    candidate = HostCandidate("ssh:measurement", HostKind.SSH, "SSH measurement", alias)
    factory = DiagnosticTaskFactory.production((candidate,))
    # A measurement must not launch authentication windows or wait for a person.
    factory.ssh_auth_broker = None
    observations = []
    fingerprint = None
    for _ in range(samples):
        started = time.monotonic()
        cpu_started = time.process_time()
        report = factory(candidate.host_id)(CancellationToken())
        elapsed_ms = (time.monotonic() - started) * 1000
        cpu_ms = (time.process_time() - cpu_started) * 1000
        current = report.host.fingerprint
        if not current or (fingerprint is not None and current != fingerprint):
            raise ValueError("SSH identity missing or changed between samples")
        fingerprint = current
        observations.append({
            "status": report.status.value,
            "elapsed_ms": round(elapsed_ms, 3),
            "process_cpu_ms": round(cpu_ms, 3),
            "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "system_observed": report.system is not None,
            "hardware_observed": report.hardware is not None,
            "ollama_connectivity": (
                report.ollama.api_connectivity.value if report.ollama else None
            ),
            "opencode_installed": report.opencode.installed if report.opencode else None,
            "runtime_prerequisites_available": bool(
                report.ollama and report.ollama.api_connectivity is ProbeStatus.OK
                and report.opencode and report.opencode.installed
            ),
        })
    durations = [item["elapsed_ms"] for item in observations]
    return {
        "schema_version": 1,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "scope": "production SSH DiagnosticTaskFactory; read-only; no interactive auth",
        "limitations": "sequential baseline; no Qt event-gap or Agent inference measurement; RSS is process lifetime peak, excluding SSH children",
        "samples": observations,
        "elapsed_median_ms": round(statistics.median(durations), 3),
        "elapsed_max_ms": max(durations),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("alias", help="trusted system OpenSSH alias")
    parser.add_argument("--samples", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(measure(args.alias, args.samples), indent=2))


if __name__ == "__main__":
    main()
