"""Validate Debian upgrade from historical 0.1.0~dev0 to final 0.1.0."""
from pathlib import Path


REPO = Path("/home/yoshimi/WorkSpace/LLM-Manager")
SOURCE = REPO / "docs/validation/debian-upgrade-ff7913b-2026-09-13.py"
replacements = {
    "debian-upgrade-ff7913b-2026-09-13": "debian-upgrade-final-2026-09-16",
    "/tmp/llm-manager-debian-upgrade-8854232-5mkwqv17/":
        "/tmp/llm-manager-final-upgrade-predecessor-8854232-20260916/",
    "/tmp/llm-manager-candidate-ff7913b-20260913/llm-manager_0.1.0_all.deb":
        "/tmp/llm-manager-final-5b7d4de-20260916/artifacts/llm-manager_0.1.0_all.deb",
    "351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243":
        "63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1",
    "/tmp/phase6-debian-upgrade-ff7913b-20260913":
        "/tmp/phase6-debian-upgrade-final-20260916",
    "ff7913bb97e896f7992720b9a43c2382970a5fc8":
        "5b7d4de03e495fe630deab952de043f945a22bd7",
}
source = SOURCE.read_text()
for old, new in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
    assert old in source, old
    source = source.replace(old, new)
assert "candidate-ff7913b" not in source
exec(compile(source, str(SOURCE), "exec"), {
    "__name__": "__main__",
    "__file__": str(Path(__file__)),
})
