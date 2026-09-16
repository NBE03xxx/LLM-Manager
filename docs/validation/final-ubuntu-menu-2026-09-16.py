"""Run final Ubuntu Wayland desktop-menu and lifecycle actions."""
import importlib.util
import hashlib
from pathlib import Path
import sys


REPO = Path("/home/yoshimi/WorkSpace/LLM-Manager")
spec = importlib.util.spec_from_file_location(
    "ubuntu_lifecycle",
    REPO / "docs/validation/ubuntu-display-b15a984-2026-09-12/lifecycle.py",
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
gate.OUT = REPO / "docs/validation/ubuntu-menu-final-2026-09-16"
gate.SNAP = "phase6-ubuntu-menu-final-20260916"
gate.DEB = Path(
    "/tmp/llm-manager-final-5b7d4de-20260916/artifacts/llm-manager_0.1.0_all.deb"
)
gate.HASH = "63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1"
gate.GUEST = "/tmp/phase6-ubuntu-menu-final-20260916.deb"


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "seal":
        (gate.OUT / "SHA256SUMS").write_text("".join(
            hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
            for path in sorted(gate.OUT.iterdir())
            if path.is_file() and path.name != "SHA256SUMS"
        ))
        raise SystemExit(0)
    gate.main(action)
    if action == "prepare":
        gate.save("artifact-identity.json", {
            "source_commit": "5b7d4de03e495fe630deab952de043f945a22bd7",
            "sha256": gate.HASH,
            "package": "llm-manager",
            "version": "0.1.0",
        })
