"""Run final-artifact environment SBOM gates in fresh namespaces.

This deliberately derives the already reviewed 2026-09-13 collectors while replacing
every artifact identity, guest path, snapshot, output path, and source commit. Run one
target at a time; completed targets refuse to overwrite their evidence directory.
"""
from pathlib import Path
import sys


REPO = Path("/home/yoshimi/WorkSpace/LLM-Manager")
FINAL_DIR = Path("/tmp/llm-manager-final-5b7d4de-20260916/artifacts")
SOURCE_COMMIT = "5b7d4de03e495fe630deab952de043f945a22bd7"
LOCAL_SHA256 = "63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1"
REMOTE_SHA256 = "ee042ece330cc62febff1e4effdb59801ca55042bc845db54e0c5d78c8eea9e4"


TARGETS = {
    "ubuntu-local": (
        "collect-ff7913b-ubuntu-sbom-2026-09-13.py",
        {
            "sbom-ff7913b-ubuntu-local-2026-09-13": "sbom-final-ubuntu-local-2026-09-16",
            "/tmp/llm-manager-candidate-ff7913b-20260913/llm-manager_0.1.0_all.deb":
                str(FINAL_DIR / "llm-manager_0.1.0_all.deb"),
            "351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243": LOCAL_SHA256,
            "ff7913bb97e896f7992720b9a43c2382970a5fc8": SOURCE_COMMIT,
            "phase6-ff7913b": "phase6-final-5b7d4de",
        },
    ),
    "ubuntu-remote": (
        "collect-ff7913b-ubuntu-remote-sbom-2026-09-13.py",
        {
            "sbom-ff7913b-ubuntu-remote-2026-09-13": "sbom-final-ubuntu-remote-2026-09-16",
            "/tmp/llm-manager-candidate-ff7913b-20260913/": str(FINAL_DIR) + "/",
            "830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d": REMOTE_SHA256,
            "ff7913bb97e896f7992720b9a43c2382970a5fc8": SOURCE_COMMIT,
            "phase6-ff7913b": "phase6-final-5b7d4de",
        },
    ),
    "debian-local": (
        "collect-ff7913b-debian-sbom-2026-09-13.py",
        {
            "sbom-ff7913b-debian-local-2026-09-13": "sbom-final-debian-local-2026-09-16",
            "/tmp/llm-manager-candidate-ff7913b-20260913/llm-manager_0.1.0_all.deb":
                str(FINAL_DIR / "llm-manager_0.1.0_all.deb"),
            "351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243": LOCAL_SHA256,
            "ff7913bb97e896f7992720b9a43c2382970a5fc8": SOURCE_COMMIT,
            "phase6-ff7913b": "phase6-final-5b7d4de",
        },
    ),
}


def main(target: str) -> None:
    filename, replacements = TARGETS[target]
    path = REPO / "docs/validation" / filename
    source = path.read_text()
    for old, new in replacements.items():
        assert old in source, (target, old)
        source = source.replace(old, new)
    assert "ff7913bb97e896f7992720b9a43c2382970a5fc8" not in source
    assert "/tmp/llm-manager-candidate-ff7913b-20260913" not in source
    exec(compile(source, str(path), "exec"), {"__name__": "__main__"})


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in TARGETS:
        raise SystemExit("usage: final-environment-sbom-2026-09-16.py " + "|".join(TARGETS))
    main(sys.argv[1])
