from __future__ import annotations

import json
import re
from dataclasses import dataclass

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken, CommandRequest, HostPort
from llm_manager.domain.errors import InvariantViolation
from llm_manager.domain.models import DiskInfo, GPUInfo, HardwareInfo, SystemInfo

_MEMINFO = re.compile(r"^(?P<key>[A-Za-z_()]+):\s+(?P<value>\d+)\s+kB$", re.MULTILINE)


def parse_os_release(content: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            continue
        if value.startswith(('"', "'")) and value.endswith(value[:1]):
            value = value[1:-1]
        values[key] = value.replace(r"\"", '"').replace(r"\\", "\\")
    return values


def parse_meminfo(content: str) -> dict[str, int]:
    return {match.group("key"): int(match.group("value")) * 1024 for match in _MEMINFO.finditer(content)}


def parse_lscpu_json(content: str) -> dict[str, str]:
    try:
        document = json.loads(content)
        rows = document["lscpu"]
        return {str(row["field"]).rstrip(":"): str(row["data"]) for row in rows}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise AdapterError("parse_failed", "invalid lscpu JSON") from error


def parse_df_posix(content: str) -> tuple[DiskInfo, ...]:
    disks: list[DiskInfo] = []
    for line in content.splitlines()[1:]:
        parts = line.split(None, 5)
        if len(parts) != 6:
            continue
        filesystem, blocks, _used, available, _capacity, mount = parts
        try:
            disks.append(DiskInfo(mount, int(blocks) * 1024, int(available) * 1024, filesystem))
        except ValueError:
            continue
    return tuple(disks)


@dataclass(slots=True)
class LinuxSystemProbe:
    timeout_ms: int = 3_000

    def inspect(self, host: HostPort, cancellation: CancellationToken) -> tuple[SystemInfo, HardwareInfo]:
        os_release = host.read_file("/etc/os-release", 128 * 1024, cancellation).decode(
            "utf-8", errors="replace"
        )
        meminfo = host.read_file("/proc/meminfo", 512 * 1024, cancellation).decode(
            "utf-8", errors="replace"
        )
        lscpu = self._command(host, ("lscpu", "-J"), "linux.lscpu", cancellation)
        uname = self._command(host, ("uname", "-srmo"), "linux.uname", cancellation).strip().split()
        disks = parse_df_posix(
            self._command(host, ("df", "-Pk", "/"), "linux.disk.root", cancellation)
        )
        gpus = self._inspect_gpus(host, cancellation)
        os_values = parse_os_release(os_release)
        cpu_values = parse_lscpu_json(lscpu)
        memory = parse_meminfo(meminfo)
        if len(uname) < 3:
            raise AdapterError("parse_failed", "invalid uname output")
        logical = _positive_int(cpu_values.get("CPU(s)"), "CPU(s)")
        physical = _optional_positive_int(cpu_values.get("Core(s) per socket"), cpu_values.get("Socket(s)"))
        return (
            SystemInfo(
                distribution=os_values.get("ID", "unknown"),
                distribution_version=os_values.get("VERSION_ID", "unknown"),
                kernel=" ".join(uname[:2]),
                architecture=uname[-1],
                disks=disks,
            ),
            HardwareInfo(
                cpu=cpu_values.get("Model name", "unknown"),
                logical_cores=logical,
                physical_cores=physical,
                ram_total_bytes=memory.get("MemTotal", 0),
                ram_available_bytes=memory.get("MemAvailable", memory.get("MemFree", 0)),
                swap_total_bytes=memory.get("SwapTotal", 0),
                swap_free_bytes=memory.get("SwapFree", 0),
                gpus=gpus,
            ),
        )

    def _command(
        self, host: HostPort, argv: tuple[str, ...], correlation_id: str, cancellation: CancellationToken
    ) -> str:
        result = host.execute_readonly(CommandRequest(argv, self.timeout_ms, correlation_id), cancellation)
        if result.timed_out:
            raise AdapterError("timeout", f"{argv[0]} timed out")
        if result.exit_code != 0:
            raise AdapterError("command_failed", f"{argv[0]} failed")
        return result.stdout

    def _inspect_gpus(self, host: HostPort, cancellation: CancellationToken) -> tuple[GPUInfo, ...]:
        pci = self._command_optional(host, ("lspci", "-Dnn"), "linux.gpu.pci", cancellation)
        if pci is None:
            return ()
        gpus = list(parse_lspci_gpus(pci))
        if any(gpu.vendor == "NVIDIA" for gpu in gpus):
            query = self._command_optional(
                host,
                (
                    "nvidia-smi",
                    "--query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu,driver_version",
                    "--format=csv,noheader,nounits",
                ),
                "linux.gpu.nvidia",
                cancellation,
            )
            if query is not None:
                nvidia = parse_nvidia_smi_csv(query)
                others = tuple(gpu for gpu in gpus if gpu.vendor != "NVIDIA")
                gpus = list(nvidia + others)
        if any(gpu.vendor == "AMD" for gpu in gpus):
            query = self._command_optional(
                host,
                (
                    "rocm-smi",
                    "--showproductname",
                    "--showmeminfo",
                    "vram",
                    "--showuse",
                    "--showtemp",
                    "--showdriverversion",
                    "--json",
                ),
                "linux.gpu.amd",
                cancellation,
            )
            if query is not None:
                gpus = list(merge_amd_telemetry(tuple(gpus), parse_rocm_smi_json(query)))
        return tuple(gpus)

    def _command_optional(
        self, host: HostPort, argv: tuple[str, ...], correlation_id: str, cancellation: CancellationToken
    ) -> str | None:
        try:
            result = host.execute_readonly(CommandRequest(argv, self.timeout_ms, correlation_id), cancellation)
        except (AdapterError, KeyError):
            return None
        if result.timed_out or result.exit_code != 0:
            return None
        return result.stdout


def _positive_int(value: str | None, field: str) -> int:
    try:
        parsed = int(value or "")
    except ValueError as error:
        raise AdapterError("parse_failed", f"invalid {field}") from error
    if parsed <= 0:
        raise AdapterError("parse_failed", f"invalid {field}")
    return parsed


def _optional_positive_int(cores: str | None, sockets: str | None) -> int | None:
    try:
        value = int(cores or "") * int(sockets or "")
        return value if value > 0 else None
    except ValueError:
        return None


def parse_lspci_gpus(content: str) -> tuple[GPUInfo, ...]:
    result: list[GPUInfo] = []
    for line in content.splitlines():
        lowered = line.lower()
        if not any(kind in lowered for kind in ("vga compatible controller", "3d controller", "display controller")):
            continue
        gpu_id = line.split(None, 1)[0] if line.split() else str(len(result))
        if re.search(r"\bnvidia\b", lowered):
            vendor = "NVIDIA"
        elif "advanced micro devices" in lowered or re.search(r"\b(?:amd|ati)\b", lowered):
            vendor = "AMD"
        elif re.search(r"\bintel\b", lowered):
            vendor = "Intel"
        else:
            vendor = "Unknown"
        name = line.split(": ", 1)[1] if ": " in line else line
        result.append(GPUInfo(gpu_id=gpu_id, vendor=vendor, name=name))
    return tuple(result)


def parse_nvidia_smi_csv(content: str) -> tuple[GPUInfo, ...]:
    result: list[GPUInfo] = []
    for line in content.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 7:
            continue
        index, name, total_mib, used_mib, utilization, temperature, driver = parts
        try:
            result.append(
                GPUInfo(
                    gpu_id=index,
                    vendor="NVIDIA",
                    name=name,
                    vram_total_bytes=int(total_mib) * 1024 * 1024,
                    vram_used_bytes=int(used_mib) * 1024 * 1024,
                    utilization_pct=float(utilization),
                    temperature_c=float(temperature),
                    driver_version=driver,
                    compute_stack="CUDA",
                )
            )
        except (ValueError, InvariantViolation):
            continue
    return tuple(result)


def parse_rocm_smi_json(content: str) -> tuple[GPUInfo, ...]:
    json_start = content.find("{")
    if json_start < 0:
        return ()
    try:
        document = json.loads(content[json_start:])
    except json.JSONDecodeError:
        return ()
    if not isinstance(document, dict):
        return ()
    system = document.get("system")
    driver = system.get("Driver version") if isinstance(system, dict) else None
    result: list[GPUInfo] = []
    for card_id in sorted(key for key in document if re.fullmatch(r"card\d+", key)):
        values = document[card_id]
        if not isinstance(values, dict):
            continue
        result.append(
            GPUInfo(
                gpu_id=card_id,
                vendor="AMD",
                name=_first_string(values, "Card Series", "Card Model") or "AMD GPU",
                vram_total_bytes=_mapping_int(values, "VRAM Total Memory (B)"),
                vram_used_bytes=_mapping_int(values, "VRAM Total Used Memory (B)"),
                utilization_pct=_mapping_float(values, "GPU use (%)"),
                temperature_c=_temperature(values),
                driver_version=driver if isinstance(driver, str) else None,
                compute_stack="ROCm",
                compute_architecture=_first_string(values, "GFX Version"),
            )
        )
    return tuple(result)


def merge_amd_telemetry(
    detected: tuple[GPUInfo, ...], telemetry: tuple[GPUInfo, ...]
) -> tuple[GPUInfo, ...]:
    iterator = iter(telemetry)
    merged: list[GPUInfo] = []
    for gpu in detected:
        if gpu.vendor != "AMD":
            merged.append(gpu)
            continue
        observed = next(iterator, None)
        if observed is None:
            merged.append(gpu)
            continue
        merged.append(
            GPUInfo(
                gpu_id=gpu.gpu_id,
                vendor=gpu.vendor,
                name=gpu.name,
                vram_total_bytes=observed.vram_total_bytes,
                vram_used_bytes=observed.vram_used_bytes,
                utilization_pct=observed.utilization_pct,
                temperature_c=observed.temperature_c,
                driver_version=observed.driver_version,
                compute_stack=observed.compute_stack,
                compute_version=observed.compute_version,
                compute_architecture=observed.compute_architecture,
            )
        )
    return tuple(merged)


def _first_string(values: dict[object, object], *keys: str) -> str | None:
    for key in keys:
        value = values.get(key)
        if isinstance(value, str) and value and value != "N/A":
            return value
    return None


def _mapping_int(values: dict[object, object], key: str) -> int | None:
    try:
        value = int(str(values[key]))
        return value if value >= 0 else None
    except (KeyError, ValueError):
        return None


def _mapping_float(values: dict[object, object], key: str) -> float | None:
    try:
        return float(str(values[key]))
    except (KeyError, ValueError):
        return None


def _temperature(values: dict[object, object]) -> float | None:
    for key, value in values.items():
        if isinstance(key, str) and key.startswith("Temperature ") and key.endswith(" (C)"):
            try:
                return float(str(value))
            except ValueError:
                continue
    return None
