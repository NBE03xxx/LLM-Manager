from dataclasses import dataclass

from llm_manager.domain.enums import ReportStatus
from llm_manager.domain.models import (
    DiagnosticReport,
    HardwareInfo,
    HostInfo,
    OllamaInfo,
    OpenCodeInfo,
    SystemInfo,
    utc_now,
)

from .errors import AdapterError, OperationCancelled
from .ports import CancellationToken, ClientAdapter, HostPort, OllamaPort, SystemDiagnosticsPort


@dataclass(slots=True)
class DiagnoseHost:
    host: HostPort
    ollama: OllamaPort
    client: ClientAdapter
    system_probe: SystemDiagnosticsPort | None = None

    def execute(self, report_id: str, cancellation: CancellationToken) -> DiagnosticReport:
        if cancellation.cancelled:
            raise OperationCancelled("diagnosis cancelled before start")
        started = utc_now()
        host_info: HostInfo = self.host.identify(cancellation)
        ollama_info: OllamaInfo | None = None
        client_info: OpenCodeInfo | None = None
        system_info: SystemInfo | None = None
        hardware_info: HardwareInfo | None = None
        failures = 0
        attempts = 2

        if self.system_probe is not None:
            attempts += 1
            try:
                system_info, hardware_info = self.system_probe.inspect(self.host, cancellation)
            except AdapterError:
                failures += 1

        try:
            ollama_info = self.ollama.inspect(self.host, cancellation)
        except AdapterError:
            failures += 1
        try:
            client_info = self.client.inspect(self.host, cancellation)
        except AdapterError:
            failures += 1

        if failures == 0:
            status = ReportStatus.COMPLETE
        elif failures == attempts:
            status = ReportStatus.FAILED
        else:
            status = ReportStatus.PARTIAL
        return DiagnosticReport(
            report_id=report_id,
            schema_version="1.0",
            host=host_info,
            status=status,
            system=system_info,
            hardware=hardware_info,
            ollama=ollama_info,
            opencode=client_info,
            started_at=started,
            completed_at=utc_now(),
        )
