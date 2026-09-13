"""New rollback operation after guest clock synchronization, never an r2 retry.

Uses the same explicit action lifecycle and manual-start UI in a fresh namespace.
"""
from pathlib import Path

source=Path(__file__).with_name('cross-vm-rollback-r2-2026-09-13.py').read_text()
source=source.replace('-r2','-r3')
exec(compile(source,__file__,'exec'),globals())
