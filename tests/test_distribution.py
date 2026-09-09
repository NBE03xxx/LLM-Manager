import json
import re
import stat
import subprocess
import tempfile
import tomllib
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DebianPackagingTests(unittest.TestCase):
    def test_release_version_surfaces_are_consistent(self) -> None:
        python_version = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]["version"]
        match = re.fullmatch(r"(\d+\.\d+\.\d+)\.dev(\d+)", python_version)
        self.assertIsNotNone(match, "development version must use PEP 440 .devN")
        debian_version = f"{match.group(1)}~dev{match.group(2)}"

        init_text = (ROOT / "src/llm_manager/__init__.py").read_text(encoding="utf-8")
        self.assertIn(f'__version__ = "{python_version}"', init_text)
        changelog = (ROOT / "debian/changelog").read_text(encoding="utf-8")
        self.assertRegex(
            changelog.splitlines()[0],
            rf"^llm-manager \({re.escape(debian_version)}\) ",
        )
        remote_control = (ROOT / "packaging/remote/control").read_text(encoding="utf-8")
        self.assertIn(f"\nVersion: {debian_version}\n", f"\n{remote_control}")

        package_surfaces = (
            (
                "llm-manager",
                ROOT / "packaging/helper-metadata.json",
                ROOT / "packaging/sbom/llm-manager.cdx.json",
                ROOT / "packaging/verify-deb.sh",
            ),
            (
                "llm-manager-remote-helper",
                ROOT / "packaging/remote/helper-metadata.json",
                ROOT / "packaging/sbom/llm-manager-remote-helper.cdx.json",
                ROOT / "packaging/remote/verify-deb.sh",
            ),
        )
        for package, metadata_path, sbom_path, verifier_path in package_surfaces:
            with self.subTest(package=package):
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                self.assertEqual(metadata["package"], package)
                self.assertEqual(metadata["package_version"], debian_version)
                sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
                component = sbom["metadata"]["component"]
                expected_ref = f"pkg:deb/{package}@{debian_version}"
                self.assertEqual(component["version"], debian_version)
                self.assertEqual(component["bom-ref"], expected_ref)
                self.assertEqual(sbom["dependencies"][0]["ref"], expected_ref)
                self.assertIn(debian_version, verifier_path.read_text(encoding="utf-8"))

        composition = (ROOT / "src/llm_manager/ui/composition.py").read_text(
            encoding="utf-8"
        )
        compatible_versions = set(
            re.findall(r'frozenset\(\{"(\d+\.\d+\.\d+~dev\d+)"\}\)', composition)
        )
        self.assertEqual(compatible_versions, {debian_version})

    def test_privileged_entry_point_is_fixed_isolated_and_executable(self) -> None:
        helper = ROOT / "packaging/bin/llm-manager-helper"
        content = helper.read_text(encoding="utf-8")
        self.assertEqual(content.splitlines()[0], "#!/usr/bin/python3 -I")
        self.assertIn("sys.dont_write_bytecode = True", content)
        self.assertLess(
            content.index("sys.dont_write_bytecode = True"),
            content.index("from llm_manager.infrastructure.helper_cli import main"),
        )
        self.assertIn("llm_manager.infrastructure.helper_cli import main", content)
        self.assertEqual(stat.S_IMODE(helper.stat().st_mode), 0o755)

        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertNotIn("[project.scripts]", pyproject)
        self.assertNotIn("llm-manager-helper =", pyproject)

    def test_deb_installs_reviewed_gui_and_privilege_boundary_files(self) -> None:
        install = (ROOT / "debian/llm-manager.install").read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            install,
            [
                "THIRD_PARTY_NOTICES.md usr/share/doc/llm-manager",
                "packaging/bin/llm-manager usr/bin",
                "packaging/bin/llm-manager-helper usr/bin",
                "packaging/desktop/io.github.nbe03xxx.llm-manager.desktop usr/share/applications",
                "packaging/icons/io.github.nbe03xxx.llm-manager.svg usr/share/icons/hicolor/scalable/apps",
                "packaging/sbom/llm-manager.cdx.json usr/share/doc/llm-manager",
                "packaging/helper-metadata.json usr/share/llm-manager",
                "packaging/polkit/io.github.nbe03xxx.llm-manager.policy usr/share/polkit-1/actions",
                "packaging/bin/llm-manager-restore-review usr/bin",
                "packaging/bin/llm-manager-restore-execute usr/bin",
                "packaging/bin/llm-manager-restore-setup usr/bin",
            ],
        )
        launcher = ROOT / "packaging/bin/llm-manager"
        self.assertEqual(launcher.read_text(encoding="utf-8").splitlines()[0], "#!/usr/bin/python3 -I")
        self.assertIn("llm_manager.ui.qt_app import main", launcher.read_text(encoding="utf-8"))
        self.assertEqual(stat.S_IMODE(launcher.stat().st_mode), 0o755)

        desktop = dict(
            line.split("=", 1)
            for line in (ROOT / "packaging/desktop/io.github.nbe03xxx.llm-manager.desktop")
            .read_text(encoding="utf-8")
            .splitlines()
            if "=" in line
        )
        self.assertEqual(desktop["Type"], "Application")
        self.assertEqual(desktop["Exec"], "/usr/bin/llm-manager")
        self.assertEqual(desktop["TryExec"], "/usr/bin/llm-manager")
        self.assertEqual(desktop["Icon"], "io.github.nbe03xxx.llm-manager")
        self.assertEqual(desktop["Terminal"], "false")
        policy = ROOT / "packaging/polkit/io.github.nbe03xxx.llm-manager.policy"
        action = ET.parse(policy).getroot().find("action")
        annotations = {item.attrib["key"]: item.text for item in action.findall("annotate")}
        self.assertEqual(
            annotations["org.freedesktop.policykit.exec.path"],
            "/usr/bin/llm-manager-helper",
        )

    def test_control_declares_runtime_and_privilege_dependencies(self) -> None:
        control = (ROOT / "debian/control").read_text(encoding="utf-8")
        for dependency in (
            "python3-all (>= 3.13)",
            "python3-cryptography (>= 43.0.0)",
            "python3-cryptography (<< 47)",
            "python3-secretstorage (>= 3.3.3)",
            "python3-secretstorage (<< 4)",
            "python3-pyside6.qtcore (>= 6.8.2.1)",
            "python3-pyside6.qtwidgets (>= 6.8.2.1)",
            "openssh-client",
            "pkexec",
            "polkitd",
            "systemd",
        ):
            self.assertIn(dependency, control)
        self.assertIn("Rules-Requires-Root: no", control)
        self.assertNotIn("pybuild-plugin-pyproject", control)
        rules = ROOT / "debian/rules"
        self.assertEqual(stat.S_IMODE(rules.stat().st_mode), 0o755)
        self.assertNotIn("sudo", rules.read_text(encoding="utf-8"))
        self.assertIn("PYBUILD_SYSTEM=distutils", rules.read_text(encoding="utf-8"))
        self.assertIn("dh_python3 --no-shebang-rewrite", rules.read_text(encoding="utf-8"))

        verifier = ROOT / "packaging/verify-deb.sh"
        self.assertEqual(stat.S_IMODE(verifier.stat().st_mode), 0o755)
        verifier_text = verifier.read_text(encoding="utf-8")
        self.assertIn("#!/usr/bin/python3 -I", verifier_text)
        self.assertIn("root/root", verifier_text)
        self.assertIn("io.github.nbe03xxx.llm-manager.desktop", verifier_text)

    def test_remote_helper_package_is_separate_and_isolated(self) -> None:
        helper = ROOT / "packaging/remote/bin/llm-manager-remote-helper"
        content = helper.read_text(encoding="utf-8")
        self.assertEqual(content.splitlines()[0], "#!/usr/bin/python3 -I")
        self.assertIn(
            'sys.path.insert(0, "/usr/lib/llm-manager-remote-helper")',
            content,
        )
        self.assertIn("sys.dont_write_bytecode = True", content)
        self.assertLess(
            content.index("sys.dont_write_bytecode = True"),
            content.index('sys.path.insert(0, "/usr/lib/llm-manager-remote-helper")'),
        )
        self.assertIn("remote_helper_cli import main", content)
        self.assertEqual(stat.S_IMODE(helper.stat().st_mode), 0o755)

        local_install = (ROOT / "debian/llm-manager.install").read_text(encoding="utf-8")
        self.assertNotIn("llm-manager-remote-helper", local_install)
        self.assertNotIn("packaging/remote", local_install)

        control = (ROOT / "packaging/remote/control").read_text(encoding="utf-8")
        self.assertIn("Package: llm-manager-remote-helper", control)
        self.assertIn("python3 (>= 3.13)", control)
        self.assertIn("python3-cryptography (>= 43.0.0)", control)
        self.assertIn("python3-cryptography (<< 47)", control)
        self.assertIn("sudo", control)
        for forbidden in ("python3-secretstorage", "openssh-client", "policykit-1", "pkexec", "polkitd"):
            self.assertNotIn(forbidden, control)

    def test_direct_dependency_sboms_are_cyclonedx_and_match_packages(self) -> None:
        expected = {
            "llm-manager.cdx.json": {
                "llm-manager",
                "python3",
                "cryptography",
                "SecretStorage",
                "PySide6",
                "OpenSSH client",
                "pkexec / polkit",
                "systemd",
            },
            "llm-manager-remote-helper.cdx.json": {
                "llm-manager-remote-helper",
                "python3",
                "cryptography",
                "sudo",
            },
        }
        for filename, names in expected.items():
            with self.subTest(filename=filename):
                document = json.loads(
                    (ROOT / "packaging/sbom" / filename).read_text(encoding="utf-8")
                )
                self.assertEqual(document["bomFormat"], "CycloneDX")
                self.assertEqual(document["specVersion"], "1.6")
                actual = {document["metadata"]["component"]["name"]}
                actual.update(component["name"] for component in document["components"])
                self.assertEqual(actual, names)

    def test_remote_helper_deb_artifact_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "llm-manager-remote-helper.deb"
            second = Path(temp_dir) / "llm-manager-remote-helper-second.deb"
            subprocess.run(
                [str(ROOT / "packaging/remote/build-deb.sh"), str(artifact)],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [str(ROOT / "packaging/remote/build-deb.sh"), str(second)],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(artifact.read_bytes(), second.read_bytes())
            subprocess.run(
                [str(ROOT / "packaging/remote/verify-deb.sh"), str(artifact)],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )


if __name__ == "__main__":
    unittest.main()
