from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from llm_manager.adapters.clients.opencode import OpenCodeReadOnlyAdapter
from llm_manager.adapters.host.local import LocalHostAdapter
from llm_manager.adapters.host.openssh import OpenSshHostAdapter
from llm_manager.adapters.ollama.readonly import OllamaReadOnlyAdapter
from llm_manager.application.host_discovery import HostCandidate
from llm_manager.application.ports import CancellationToken
from llm_manager.application.services import DiagnoseHost
from llm_manager.diagnostics.linux import LinuxSystemProbe
from llm_manager.domain.enums import HostKind
from llm_manager.domain.models import DiagnosticReport
from llm_manager.infrastructure.process import ProcessPolicy, SubprocessRunner

_LOCAL_EXECUTABLES = frozenset(
    {"curl", "df", "lscpu", "lspci", "nvidia-smi", "ollama", "opencode", "rocm-smi", "systemctl", "uname"}
)


@dataclass(slots=True)
class DiagnosticTaskFactory:
    hosts: tuple[HostCandidate, ...]
    local_runner: SubprocessRunner
    ssh_runner: SubprocessRunner
    local_config_candidates: tuple[str, ...]
    remote_config_candidates: tuple[str, ...] = ()

    @classmethod
    def production(cls, hosts: tuple[HostCandidate, ...]) -> "DiagnosticTaskFactory":
        return cls(
            hosts=hosts,
            local_runner=SubprocessRunner(ProcessPolicy(_LOCAL_EXECUTABLES)),
            ssh_runner=SubprocessRunner(ProcessPolicy(frozenset({"ssh"}))),
            local_config_candidates=_local_opencode_candidates(),
        )

    def __call__(self, host_id: str):
        candidate = next((item for item in self.hosts if item.host_id == host_id), None)
        if candidate is None:
            raise ValueError("unknown_host_candidate")
        service = self._service(candidate)
        report_id = f"diagnosis-{uuid.uuid4().hex}"

        def execute(cancellation: CancellationToken) -> DiagnosticReport:
            return service.execute(report_id, cancellation)

        return execute

    def _service(self, candidate: HostCandidate) -> DiagnoseHost:
        if candidate.kind is HostKind.LOCAL:
            host = LocalHostAdapter(self.local_runner, display_name=candidate.display_name)
            configs = self.local_config_candidates
        else:
            if candidate.ssh_alias is None:
                raise ValueError("ssh_candidate_requires_alias")
            host = OpenSshHostAdapter(candidate.ssh_alias, self.ssh_runner, candidate.display_name)
            configs = self.remote_config_candidates
        return DiagnoseHost(
            host=host,
            ollama=OllamaReadOnlyAdapter(),
            client=OpenCodeReadOnlyAdapter(configs),
            system_probe=LinuxSystemProbe(),
        )


def _local_opencode_candidates() -> tuple[str, ...]:
    configured = os.environ.get("XDG_CONFIG_HOME")
    root = Path(configured) if configured and Path(configured).is_absolute() else Path.home() / ".config"
    directory = root / "opencode"
    return tuple(str(directory / name) for name in ("opencode.jsonc", "opencode.json", "config.json"))
