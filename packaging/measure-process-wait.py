"""Phase 6 isolated subprocess baseline; run with PYTHONPATH=src.

This measures the production process adapter, not Qt or an installed Agent.
Only the child created here is cancelled; no product configuration is touched.
"""
from __future__ import annotations

import json
import os
import platform
import resource
import sys
import tempfile
import threading
import time
from pathlib import Path

from llm_manager.application.errors import OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandRequest
from llm_manager.infrastructure.process import ProcessPolicy, SubprocessRunner


def sample(mode: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="llm-manager-process-gate-") as directory:
        ready = Path(directory) / "ready"
        # Acknowledgement proves both pipes are closed before requesting cancel.
        child = (
            "import os,time,pathlib; os.close(1); os.close(2); "
            f"pathlib.Path({str(ready)!r}).write_text(str(os.getpid())); "
            f"time.sleep({0.2 if mode == 'complete' else 3})"
        )
        token = CancellationToken()
        observed: dict[str, object] = {}

        def cancel() -> None:
            deadline = time.monotonic() + 2
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.005)
            if not ready.exists():
                observed["ready_missing"] = True
                return
            time.sleep(0.2)
            observed["cancel_requested"] = time.monotonic()
            token.cancel()

        thread = threading.Thread(target=cancel) if mode == "cancel" else None
        runner = SubprocessRunner(ProcessPolicy({sys.executable}))
        cpu = time.process_time()
        started = time.monotonic()
        if thread:
            thread.start()
        try:
            result = runner.run(
                CommandRequest((sys.executable, "-c", child), 400 if mode == "timeout" else 5000, "phase6-gate"),
                token,
            )
            outcome = "timeout" if result.timed_out else "complete"
            assert result.timed_out or result.exit_code == 0
        except OperationCancelled:
            outcome = "cancel"
        finally:
            finished = time.monotonic()
            cpu_ms = (time.process_time() - cpu) * 1000
            if thread:
                thread.join()
        assert outcome == mode, (mode, outcome)
        assert ready.exists() and not observed.get("ready_missing")
        pid = int(ready.read_text())
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            reaped = True
        else:
            reaped = False
        assert reaped, "child was not reaped by the adapter"
        return {
            "mode": mode,
            "elapsed_ms": round((finished - started) * 1000, 3),
            "cancel_to_reaped_ms": round((finished - observed["cancel_requested"]) * 1000, 3) if mode == "cancel" else None,
            "parent_cpu_ms": round(cpu_ms, 3),
            "parent_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "reaped": reaped,
        }


if __name__ == "__main__":
    print(json.dumps({
        "python": platform.python_version(),
        "platform": platform.platform(),
        "scope": "production SubprocessRunner with isolated synthetic child; cumulative parent RSS; no Qt",
        "samples": [sample(mode) for mode in ("complete", "timeout", "cancel") for _ in range(5)],
    }, indent=2))
