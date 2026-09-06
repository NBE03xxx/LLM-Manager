"""Isolated Phase 6 Qt/production subprocess gate; requires system PySide6.

Run from a source checkout with PYTHONPATH=src. No installed Agent or user
configuration is used. Each child is finite and confined to a temporary root.
"""
from __future__ import annotations

import json
import os
import platform
import resource
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import __version__ as qt_version
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QPushButton

from llm_manager.application.errors import OperationCancelled
from llm_manager.application.ports import CommandRequest
from llm_manager.infrastructure.process import ProcessPolicy, SubprocessRunner
from llm_manager.ui.qt_window import MainWindow
from llm_manager.ui.qt_worker import QtTaskRunner, QtWorkerCoordinator


def sample(mode: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="llm-manager-qt-process-") as directory:
        ready = Path(directory) / "ready"
        child = (
            "import os,time,pathlib; os.close(1); os.close(2); "
            f"pathlib.Path({str(ready)!r}).write_text(str(os.getpid())); "
            f"time.sleep({0.3 if mode == 'complete' else 10})"
        )
        process = SubprocessRunner(ProcessPolicy({sys.executable}))
        observed = {}
        loop = QEventLoop()

        def task(token):
            try:
                result = process.run(
                    CommandRequest((sys.executable, "-c", child), 500 if mode == "timeout" else 15000, "qt-process-gate"),
                    token,
                )
                observed["outcome"] = "timeout" if result.timed_out else "complete"
                observed["exit_code"] = result.exit_code
                return result
            except OperationCancelled:
                observed["outcome"] = "cancel"
                raise
            finally:
                observed["adapter_finished"] = time.monotonic()

        window = MainWindow(lambda _host: task) if mode == "close" else None
        coordinator = QtWorkerCoordinator()
        runner = QtTaskRunner(task) if window is None else None
        if runner:
            runner.signals.finished.connect(loop.quit)
            runner.signals.error.connect(lambda error: observed.update(error=error.code))
        ticks = []
        started = time.monotonic()
        cpu = time.process_time()
        sentinel = QTimer()
        sentinel.setInterval(10)

        def tick():
            now = time.monotonic()
            ticks.append(now)
            if ready.exists() and "ready_at" not in observed:
                observed["ready_at"] = now
            if mode in ("cancel", "close") and "ready_at" in observed and "cancel_at" not in observed:
                if now - observed["ready_at"] >= 5:
                    observed["cancel_at"] = now
                    if window:
                        window.close()
                        observed["close_deferred"] = window.isVisible()
                    else:
                        coordinator.cancel("gate")
            if window and not window.isVisible() and "adapter_finished" in observed:
                loop.quit()

        sentinel.timeout.connect(tick)
        sentinel.start()
        if window:
            window.show()
            window.findChild(QPushButton, "start-diagnosis").click()
        else:
            coordinator.start("gate", runner)
        loop.exec()
        finished = time.monotonic()
        sentinel.stop()
        QApplication.processEvents()
        assert observed.get("outcome") == ("cancel" if mode == "close" else mode), observed
        assert "error" not in observed, observed
        if mode == "complete":
            assert observed["exit_code"] == 0
        assert not coordinator.is_active("gate")
        if window:
            assert observed["close_deferred"] and not window.isVisible()
            window.deleteLater()
        pid = int(ready.read_text())
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass
        else:
            raise AssertionError("child not reaped by adapter")
        timeline = [started, *ticks, finished]
        gap_ms = max(b - a for a, b in zip(timeline, timeline[1:])) * 1000
        assert len(ticks) >= 10 and gap_ms < 250, (len(ticks), gap_ms)
        cancel_ms = ((observed["adapter_finished"] - observed["cancel_at"]) * 1000
                     if "cancel_at" in observed else None)
        assert cancel_ms is None or cancel_ms < 500
        return {
            "mode": mode,
            "elapsed_ms": round((finished - started) * 1000, 3),
            "ticks": len(ticks),
            "max_event_gap_ms": round(gap_ms, 3),
            "cancel_to_reaped_ms": round(cancel_ms, 3) if cancel_ms is not None else None,
            "close_to_hidden_ms": round((finished - observed["cancel_at"]) * 1000, 3) if window else None,
            "parent_cpu_ms": round((time.process_time() - cpu) * 1000, 3),
            "parent_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "reaped": True,
        }


if __name__ == "__main__":
    application = QApplication([])
    application.setQuitOnLastWindowClosed(False)
    print(json.dumps({
        "python": platform.python_version(), "pyside6": qt_version,
        "platform": platform.platform(),
        "scope": "offscreen Qt + production SubprocessRunner; synthetic finite child; cumulative parent RSS",
        "samples": [sample(mode) for mode in ("complete", "timeout", "cancel", "close") for _ in range(3)],
    }, indent=2))
