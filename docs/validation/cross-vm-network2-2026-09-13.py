"""Fresh network gate. Start watch BEFORE launch; preserve the earlier attempt."""
from pathlib import Path

source=Path(__file__).with_name('cross-vm-network-2026-09-13.py').read_text()
source=source.replace('phase6-cross-vm-net','phase6-cross-vm-net2')
source=source.replace('cross-vm-network-2026-09-13','cross-vm-network2-2026-09-13')
exec(compile(source,__file__,'exec'),globals())
