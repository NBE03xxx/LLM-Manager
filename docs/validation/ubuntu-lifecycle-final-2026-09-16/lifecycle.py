"""Run final local/remote Ubuntu lifecycle gates in separate snapshots."""
from pathlib import Path
import sys


REPO = Path("/home/yoshimi/WorkSpace/LLM-Manager")
SOURCE = REPO / "docs/validation/lifecycle-ff7913b-2026-09-13.py"
FINAL = Path("/tmp/llm-manager-final-5b7d4de-20260916/artifacts")
OLD = Path("/tmp/llm-manager-final-upgrade-predecessor-8854232-20260916")

replacements = {
    "/tmp/llm-manager-candidate-ff7913b-20260913": str(FINAL),
    "ff7913bb97e896f7992720b9a43c2382970a5fc8":
        "5b7d4de03e495fe630deab952de043f945a22bd7",
    "remote-helper-ff7913b-2026-09-13": "remote-helper-final-2026-09-16",
    "phase6-remote-helper-ff7913b-20260913": "phase6-remote-helper-final-20260916",
    "3fe79afe4e1d72ca8e9dfea94cd514154a2fdb099d79671174a7601e44adf52f":
        "84213a1c9b897919c7d5625c7361be2ec7c74f4734db4fa9e50f29125141c5fa",
    "830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d":
        "ee042ece330cc62febff1e4effdb59801ca55042bc845db54e0c5d78c8eea9e4",
    "/tmp/phase6-remote-helper-ff7913b-20260913":
        "/tmp/phase6-remote-helper-final-20260916",
    "ubuntu-lifecycle-ff7913b-2026-09-13": "ubuntu-lifecycle-final-2026-09-16",
    "phase6-ubuntu-lifecycle-ff7913b-20260913": "phase6-ubuntu-lifecycle-final-20260916",
    "351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243":
        "63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1",
    "/tmp/phase6-ubuntu-lifecycle-ff7913b.deb":
        "/tmp/phase6-ubuntu-lifecycle-final.deb",
}

source = SOURCE.read_text()
needle = "gate.NEW_SOURCE_COMMIT = COMMIT\n"
assert needle in source
source = source.replace(
    needle,
    needle + f"    gate.OLD_ARTIFACT = Path({str(OLD / 'llm-manager-remote-helper_0.1.0~dev0_all.deb')!r})\n",
)
for old, new in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
    assert old in source, old
    source = source.replace(old, new)
assert "candidate-ff7913b" not in source
exec(compile(source, str(SOURCE), "exec"), {
    "__name__": "__main__",
    "__file__": str(Path(__file__)),
    "sys": sys,
})
