import unittest

from llm_manager.application.ports import CancellationToken, CommandResult
from llm_manager.diagnostics.linux import (
    LinuxSystemProbe,
    parse_df_posix,
    parse_lscpu_json,
    parse_lspci_gpus,
    parse_meminfo,
    parse_nvidia_smi_csv,
    parse_os_release,
    parse_rocm_smi_json,
)
from llm_manager.domain.enums import HostKind
from llm_manager.adapters.fakes import FakeHostAdapter

from tests.fixtures import host_info


class LinuxParserTests(unittest.TestCase):
    def test_os_release(self) -> None:
        self.assertEqual(parse_os_release('ID=ubuntu\nVERSION_ID="26.04"\n')["VERSION_ID"], "26.04")

    def test_meminfo_normalizes_kib_to_bytes(self) -> None:
        self.assertEqual(parse_meminfo("MemTotal:       1024 kB\n")["MemTotal"], 1024 * 1024)

    def test_lscpu_json(self) -> None:
        self.assertEqual(parse_lscpu_json('{"lscpu":[{"field":"CPU(s):","data":"8"}]}')["CPU(s)"], "8")

    def test_df_posix(self) -> None:
        disks = parse_df_posix("Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/x 100 30 70 30% /\n")
        self.assertEqual(disks[0].free_bytes, 70 * 1024)

    def test_detects_amd_and_nvidia_pci_devices(self) -> None:
        content = (
            "0000:01:00.0 VGA compatible controller: NVIDIA Corporation Test GPU [10de:1234]\n"
            "0000:02:00.0 Display controller: Advanced Micro Devices, Inc. [AMD/ATI] Test GPU [1002:1234]\n"
        )
        self.assertEqual([gpu.vendor for gpu in parse_lspci_gpus(content)], ["NVIDIA", "AMD"])

    def test_parses_nvidia_metrics(self) -> None:
        gpu = parse_nvidia_smi_csv("0, RTX Test, 24576, 1024, 25, 61, 590.1\n")[0]
        self.assertEqual(gpu.vram_total_bytes, 24576 * 1024 * 1024)
        self.assertEqual(gpu.utilization_pct, 25)

    def test_compatible_controller_does_not_false_match_ati(self) -> None:
        content = "0000:00:01.0 VGA compatible controller: Red Hat, Inc. QXL paravirtual graphic card [1b36:0100]\n"
        self.assertEqual(parse_lspci_gpus(content)[0].vendor, "Unknown")

    def test_parses_rocm_json_with_missing_temperature(self) -> None:
        content = 'WARNING before JSON\n{"card0":{"GPU use (%)":"0","VRAM Total Memory (B)":"17095983104","VRAM Total Used Memory (B)":"59891712","Card Series":"N/A","Card Model":"0x7590","GFX Version":"gfx1200"},"system":{"Driver version":"7.0.0-30-generic"}}'
        gpu = parse_rocm_smi_json(content)[0]
        self.assertEqual(gpu.vram_total_bytes, 17095983104)
        self.assertEqual(gpu.vram_used_bytes, 59891712)
        self.assertEqual(gpu.utilization_pct, 0)
        self.assertIsNone(gpu.temperature_c)
        self.assertEqual(gpu.compute_stack, "ROCm")
        self.assertEqual(gpu.compute_architecture, "gfx1200")


class LinuxProbeTests(unittest.TestCase):
    def test_builds_system_and_hardware(self) -> None:
        host = FakeHostAdapter(
            host_info(HostKind.LOCAL),
            files={
                "/etc/os-release": b'ID=ubuntu\nVERSION_ID="26.04"\n',
                "/proc/meminfo": b"MemTotal: 1000 kB\nMemAvailable: 750 kB\nSwapTotal: 500 kB\nSwapFree: 400 kB\n",
            },
            command_results={
                ("lscpu", "-J"): CommandResult(("lscpu", "-J"), 0, '{"lscpu":[{"field":"CPU(s):","data":"8"},{"field":"Model name:","data":"Test CPU"},{"field":"Core(s) per socket:","data":"4"},{"field":"Socket(s):","data":"1"}]}', "", False, 1),
                ("uname", "-srmo"): CommandResult(("uname", "-srmo"), 0, "Linux 6.18 GNU/Linux x86_64\n", "", False, 1),
                ("df", "-Pk", "/"): CommandResult(("df", "-Pk", "/"), 0, "Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/x 100 30 70 30% /\n", "", False, 1),
                ("lspci", "-Dnn"): CommandResult(("lspci", "-Dnn"), 0, "", "", False, 1),
            },
        )
        system, hardware = LinuxSystemProbe().inspect(host, CancellationToken())
        self.assertEqual(system.distribution_version, "26.04")
        self.assertEqual(hardware.logical_cores, 8)
        self.assertEqual(hardware.physical_cores, 4)


if __name__ == "__main__":
    unittest.main()
