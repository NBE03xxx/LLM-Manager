from __future__ import annotations

from dataclasses import dataclass

from llm_manager.domain.enums import ProbeStatus
from llm_manager.domain.models import DiagnosticReport

from .i18n import Catalog


@dataclass(frozen=True, slots=True)
class DiagnosticPageView:
    summary: str
    items: tuple[str, ...]


def present_diagnostic_report(
    report: DiagnosticReport, catalog: Catalog
) -> DiagnosticPageView:
    probes = report.probe_results
    probe_issues = tuple(
        (name, result)
        for name, result in probes
        if result.status is not ProbeStatus.OK
    )
    items = [
        catalog.text(
            "diagnosis.host",
            name=report.host.display_name,
            kind=report.host.kind.value,
            hostname=report.host.hostname or catalog.text("diagnosis.unknown"),
        )
    ]

    if report.system is None:
        items.append(catalog.text("diagnosis.system_unavailable"))
    else:
        system = report.system
        items.append(
            catalog.text(
                "diagnosis.system",
                distribution=system.distribution,
                version=system.distribution_version,
                kernel=system.kernel,
                architecture=system.architecture,
                disks=len(system.disks),
            )
        )

    if report.hardware is None:
        items.append(catalog.text("diagnosis.hardware_unavailable"))
    else:
        hardware = report.hardware
        items.append(
            catalog.text(
                "diagnosis.hardware",
                cpu=hardware.cpu,
                cores=hardware.logical_cores,
                available=_format_bytes(hardware.ram_available_bytes),
                total=_format_bytes(hardware.ram_total_bytes),
                gpus=len(hardware.gpus),
            )
        )

    ollama = report.ollama
    if ollama is None:
        items.append(catalog.text("diagnosis.ollama_unavailable"))
    else:
        items.append(
            catalog.text(
                "diagnosis.ollama",
                installed=_yes_no(ollama.installed, catalog),
                version=ollama.version or catalog.text("diagnosis.unknown"),
                api=ollama.api_connectivity.value,
                models=len(ollama.models),
                loaded=len(ollama.loaded_models),
            )
        )

    opencode = report.opencode
    if opencode is None:
        items.append(catalog.text("diagnosis.opencode_unavailable"))
    else:
        items.append(
            catalog.text(
                "diagnosis.opencode",
                installed=_yes_no(opencode.installed, catalog),
                version=opencode.version or catalog.text("diagnosis.unknown"),
                provider=opencode.provider or catalog.text("diagnosis.unknown"),
                model=opencode.model or catalog.text("diagnosis.unknown"),
                warnings=len(opencode.parse_warnings),
            )
        )

    for name, result in probe_issues:
        items.append(
            catalog.text(
                "diagnosis.probe_issue",
                name=name,
                status=result.status.value,
                code=result.error_code or catalog.text("diagnosis.none"),
            )
        )
    for finding in report.findings:
        items.append(
            catalog.text(
                "diagnosis.finding",
                severity=catalog.text(f"severity.{finding.severity.value}"),
                summary=catalog.text(
                    finding.summary.message_key, **dict(finding.summary.arguments)
                ),
            )
        )

    return DiagnosticPageView(
        summary=catalog.text(
            "diagnosis.summary",
            host=report.host.display_name,
            status=catalog.text(f"diagnosis.status.{report.status.value}"),
            ok=sum(result.status is ProbeStatus.OK for _, result in probes),
            total=len(probes),
            issues=len(probe_issues) + len(report.findings),
        ),
        items=tuple(items),
    )


def _yes_no(value: bool, catalog: Catalog) -> str:
    return catalog.text("diagnosis.yes" if value else "diagnosis.no")


def _format_bytes(value: int) -> str:
    amount = float(value)
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units[:-1]:
        if amount < 1024:
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} {units[-1]}"
