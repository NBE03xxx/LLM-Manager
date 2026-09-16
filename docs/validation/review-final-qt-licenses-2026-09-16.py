"""Review Qt/PySide6 evidence from the three final-artifact environments."""
from pathlib import Path


REPO = Path("/home/yoshimi/WorkSpace/LLM-Manager")
SOURCE = REPO / "docs/validation/review-ff7913b-qt-licenses-2026-09-13.py"
replacements = {
    "qt-license-review-ff7913b-2026-09-13.json":
        "qt-license-review-final-2026-09-16.json",
    "sbom-ff7913b-ubuntu-local-2026-09-13":
        "sbom-final-ubuntu-local-2026-09-16",
    "sbom-ff7913b-ubuntu-remote-2026-09-13":
        "sbom-final-ubuntu-remote-2026-09-16",
    "sbom-ff7913b-debian-local-2026-09-13":
        "sbom-final-debian-local-2026-09-16",
    "ff7913bb97e896f7992720b9a43c2382970a5fc8":
        "5b7d4de03e495fe630deab952de043f945a22bd7",
}
source = SOURCE.read_text()
for old, new in replacements.items():
    assert old in source, old
    source = source.replace(old, new)
assert "sbom-ff7913b" not in source
exec(compile(source, str(SOURCE), "exec"), {"__name__": "__main__"})
