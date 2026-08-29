import stat
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DebianPackagingTests(unittest.TestCase):
    def test_privileged_entry_point_is_fixed_isolated_and_executable(self) -> None:
        helper = ROOT / "packaging/bin/llm-manager-helper"
        content = helper.read_text(encoding="utf-8")
        self.assertEqual(content.splitlines()[0], "#!/usr/bin/python3 -I")
        self.assertIn("llm_manager.infrastructure.helper_cli import main", content)
        self.assertEqual(stat.S_IMODE(helper.stat().st_mode), 0o755)

        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertNotIn("[project.scripts]", pyproject)
        self.assertNotIn("llm-manager-helper =", pyproject)

    def test_deb_installs_only_reviewed_privilege_boundary_files(self) -> None:
        install = (ROOT / "debian/llm-manager.install").read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            install,
            [
                "packaging/bin/llm-manager-helper usr/bin",
                "packaging/helper-metadata.json usr/share/llm-manager",
                "packaging/polkit/io.github.nbe03xxx.llm-manager.policy usr/share/polkit-1/actions",
            ],
        )
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
            "python3-all (>= 3.14)",
            "python3-cryptography (>= 46.0.5)",
            "python3-secretstorage (>= 3.5)",
            "openssh-client",
            "policykit-1",
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


if __name__ == "__main__":
    unittest.main()
