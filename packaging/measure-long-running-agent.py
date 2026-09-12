"""Measure a bounded long-running Agent-like task through the production Qt boundary.

The release Gate duration is 3600 seconds. Shorter durations are preflight-only and
are identified as such in the JSON result. The workload is synthetic: it exercises
Qt worker, GUI cancellation, bounded subprocess output, CPU work and a fixed memory
working set without reading or changing user configuration.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
import textwrap
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from llm_manager.application.ports import CommandRequest
from llm_manager.infrastructure.process import ProcessPolicy, SubprocessRunner
from llm_manager.ui.qt_window import MainWindow
from llm_manager.ui.qt_worker import QtWorkerCoordinator
from llm_manager.ui.workflow import GuiPresenter, WorkflowStatus


RELEASE_GATE_SECONDS = 3600.0
TICK_INTERVAL_MS = 50
RSS_SAMPLE_SECONDS = 1.0
MAX_EVENT_GAP_MS = 250.0
MAX_CANCEL_TO_REAP_MS = 1000.0
MAX_PARENT_RSS_GROWTH_KIB = 64 * 1024
MAX_PARENT_CPU_FRACTION = 0.25
MAX_CHILD_RSS_KIB = 128 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=float, default=RELEASE_GATE_SECONDS)
    arguments = parser.parse_args()
    if arguments.duration_seconds < 5:
        parser.error("duration must be at least 5 seconds")
    return arguments


def rss_kib(pid: int) -> int | None:
    try:
        lines = Path(f"/proc/{pid}/status").read_text().splitlines()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return None
    for line in lines:
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    return None


def agent_program(duration_seconds: float, ready: Path, heartbeat: Path) -> str:
    return textwrap.dedent(
        f"""
        import hashlib
        import json
        import os
        from pathlib import Path
        import time

        duration={duration_seconds + 300.0!r}
        ready=Path({str(ready)!r})
        heartbeat=Path({str(heartbeat)!r})
        working=bytearray(32 * 1024 * 1024)
        for offset in range(0, len(working), 4096):
            working[offset] = offset % 251
        ready.write_text(str(os.getpid()))
        started=time.monotonic()
        sequence=0
        while time.monotonic() - started < duration:
            offset=sequence % (31 * 1024 * 1024)
            digest=hashlib.sha256(memoryview(working)[offset:offset + 1024 * 1024]).hexdigest()
            sequence += 1
            if sequence == 1 or sequence % 20 == 0:
                elapsed=round(time.monotonic() - started, 3)
                record={{'sequence':sequence,'elapsed_seconds':elapsed,'digest':digest}}
                print(json.dumps(record,sort_keys=True),flush=True)
                temporary=heartbeat.with_suffix('.tmp')
                temporary.write_text(json.dumps(record,sort_keys=True)+'\\n')
                os.replace(temporary,heartbeat)
            time.sleep(0.2)
        """
    )


def run(duration_seconds: float) -> dict[str, object]:
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    with tempfile.TemporaryDirectory(prefix="llm-manager-long-agent-") as directory:
        root = Path(directory)
        ready = root / "ready"
        heartbeat = root / "heartbeat.json"
        process = SubprocessRunner(ProcessPolicy({sys.executable}, max_output_bytes=1024 * 1024))
        observed: dict[str, object] = {}

        def task(cancellation):
            observed["worker_started_at"] = time.monotonic()
            try:
                return process.run(
                    CommandRequest(
                        (sys.executable, "-I", "-c", agent_program(duration_seconds, ready, heartbeat)),
                        round((duration_seconds + 600.0) * 1000),
                        "long-running-agent-gate",
                    ),
                    cancellation,
                )
            finally:
                observed["adapter_finished_at"] = time.monotonic()

        presenter = GuiPresenter()
        coordinator = QtWorkerCoordinator()
        window = MainWindow(
            lambda _host: task,
            presenter=presenter,
            coordinator=coordinator,
        )
        window.resize(800, 600)
        window.show()
        start_button = window.findChild(QPushButton, "start-diagnosis")
        cancel_button = window.findChild(QPushButton, "cancel-operation")
        status_label = window.findChild(QLabel, "workflow-status")
        assert start_button is not None and cancel_button is not None and status_label is not None

        loop = QEventLoop()
        started = time.monotonic()
        cpu_started = time.process_time()
        parent_initial_rss = rss_kib(os.getpid())
        assert parent_initial_rss is not None
        state: dict[str, object] = {
            "ticks": 0,
            "max_event_gap_ms": 0.0,
            "last_tick": started,
            "last_rss_sample": 0.0,
            "parent_rss_samples_kib": [],
            "child_rss_samples_kib": [],
            "child_pid": None,
            "watchdog": False,
        }

        def tick() -> None:
            now = time.monotonic()
            gap_ms = (now - float(state["last_tick"])) * 1000
            state["last_tick"] = now
            state["ticks"] = int(state["ticks"]) + 1
            state["max_event_gap_ms"] = max(float(state["max_event_gap_ms"]), gap_ms)
            elapsed = now - started
            if state["child_pid"] is None and ready.exists():
                state["child_pid"] = int(ready.read_text())
                observed["child_ready_at"] = now
            if elapsed - float(state["last_rss_sample"]) >= RSS_SAMPLE_SECONDS:
                state["last_rss_sample"] = elapsed
                parent_rss = rss_kib(os.getpid())
                if parent_rss is not None:
                    state["parent_rss_samples_kib"].append(parent_rss)  # type: ignore[union-attr]
                if isinstance(state["child_pid"], int):
                    child_rss = rss_kib(state["child_pid"])
                    if child_rss is not None:
                        state["child_rss_samples_kib"].append(child_rss)  # type: ignore[union-attr]
            if (
                elapsed >= duration_seconds
                and state["child_pid"] is not None
                and "cancel_requested_at" not in observed
            ):
                observed["status_before_cancel"] = presenter.state.status.value
                observed["status_text_before_cancel"] = status_label.text()
                observed["cancel_enabled_before"] = cancel_button.isEnabled()
                observed["start_enabled_before"] = start_button.isEnabled()
                observed["cancel_requested_at"] = now
                cancel_button.click()
                observed["status_after_cancel_request"] = presenter.state.status.value
                observed["status_text_after_cancel_request"] = status_label.text()
            if "cancel_requested_at" in observed and not coordinator.is_active("local"):
                if not presenter.state.busy:
                    observed["finished_at"] = now
                    loop.quit()

        def watchdog() -> None:
            state["watchdog"] = True
            loop.quit()

        timer = QTimer()
        timer.setInterval(TICK_INTERVAL_MS)
        timer.timeout.connect(tick)
        timer.start()
        QTimer.singleShot(round((duration_seconds + 15.0) * 1000), watchdog)
        start_button.click()
        observed["status_after_start"] = presenter.state.status.value
        observed["status_text_after_start"] = status_label.text()
        loop.exec()
        timer.stop()
        QApplication.processEvents()

        finished = time.monotonic()
        elapsed = finished - started
        parent_samples = state["parent_rss_samples_kib"]
        child_samples = state["child_rss_samples_kib"]
        assert isinstance(parent_samples, list) and parent_samples
        assert isinstance(child_samples, list) and child_samples
        child_pid = state["child_pid"]
        assert isinstance(child_pid, int)
        try:
            os.waitpid(child_pid, os.WNOHANG)
        except ChildProcessError:
            child_reaped = True
        else:
            child_reaped = False

        heartbeat_document = json.loads(heartbeat.read_text())
        heartbeat_age = (
            float(observed["cancel_requested_at"])
            - float(observed["child_ready_at"])
            - float(heartbeat_document["elapsed_seconds"])
        )
        cancel_to_reap_ms = (
            float(observed["adapter_finished_at"]) - float(observed["cancel_requested_at"])
        ) * 1000
        parent_growth = max(parent_samples) - parent_initial_rss
        cpu_fraction = (time.process_time() - cpu_started) / elapsed
        release_duration_met = duration_seconds >= RELEASE_GATE_SECONDS
        checks = {
            "duration_met": elapsed >= duration_seconds,
            "release_duration_met": release_duration_met,
            "gui_running_state": observed.get("status_after_start") == WorkflowStatus.RUNNING.value,
            "gui_cancel_requested_state": observed.get("status_after_cancel_request")
            == WorkflowStatus.CANCEL_REQUESTED.value,
            "gui_terminal_state": presenter.state.status is WorkflowStatus.FAILED
            and presenter.state.error_code == "operation_cancelled",
            "buttons_during_run": observed.get("cancel_enabled_before") is True
            and observed.get("start_enabled_before") is False,
            "event_gap_bounded": float(state["max_event_gap_ms"]) < MAX_EVENT_GAP_MS,
            "cancel_bounded": cancel_to_reap_ms < MAX_CANCEL_TO_REAP_MS,
            "parent_rss_growth_bounded": parent_growth <= MAX_PARENT_RSS_GROWTH_KIB,
            "parent_cpu_bounded": cpu_fraction <= MAX_PARENT_CPU_FRACTION,
            "child_rss_bounded": max(child_samples) <= MAX_CHILD_RSS_KIB,
            "heartbeat_recent": heartbeat_age <= 10.0,
            "child_reaped": child_reaped,
            "worker_inactive": not coordinator.is_active("local"),
            "watchdog_not_used": state["watchdog"] is False,
        }
        required = {key: value for key, value in checks.items() if key != "release_duration_met"}
        assert all(required.values()), (checks, observed, state)
        if release_duration_met:
            assert checks["release_duration_met"]

        result = {
            "gate": "release" if release_duration_met else "preflight",
            "requested_duration_seconds": duration_seconds,
            "elapsed_seconds": round(elapsed, 3),
            "python": platform.python_version(),
            "pyside6": pyside_version,
            "platform": platform.platform(),
            "workload": "synthetic Agent-like subprocess; fixed 32 MiB working set; periodic progress",
            "limitations": "no model inference, network API, user configuration, or mutation",
            "thresholds": {
                "release_gate_seconds": RELEASE_GATE_SECONDS,
                "max_event_gap_ms": MAX_EVENT_GAP_MS,
                "max_cancel_to_reap_ms": MAX_CANCEL_TO_REAP_MS,
                "max_parent_rss_growth_kib": MAX_PARENT_RSS_GROWTH_KIB,
                "max_parent_cpu_fraction": MAX_PARENT_CPU_FRACTION,
                "max_child_rss_kib": MAX_CHILD_RSS_KIB,
            },
            "measurements": {
                "ticks": state["ticks"],
                "max_event_gap_ms": round(float(state["max_event_gap_ms"]), 3),
                "cancel_to_reap_ms": round(cancel_to_reap_ms, 3),
                "parent_initial_rss_kib": parent_initial_rss,
                "parent_peak_rss_kib": max(parent_samples),
                "parent_rss_growth_kib": parent_growth,
                "parent_cpu_fraction": round(cpu_fraction, 6),
                "child_peak_rss_kib": max(child_samples),
                "rss_sample_count": len(parent_samples),
                "heartbeat_sequence": heartbeat_document["sequence"],
                "heartbeat_age_seconds_at_cancel": round(heartbeat_age, 3),
                "status_after_start": observed["status_after_start"],
                "status_after_cancel_request": observed["status_after_cancel_request"],
                "terminal_status": presenter.state.status.value,
                "terminal_error_code": presenter.state.error_code,
            },
            "checks": checks,
        }
        window.close()
        window.deleteLater()
        QApplication.processEvents()
        return result


if __name__ == "__main__":
    args = parse_args()
    print(json.dumps(run(args.duration_seconds), indent=2, sort_keys=True))
