from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from llm_manager.application.errors import OperationCancelled
from llm_manager.application.ports import CancellationToken

T = TypeVar("T")


class QtUnavailableError(RuntimeError):
    pass


try:
    from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
except ImportError:
    PYSIDE_AVAILABLE = False

    class QtTaskRunner(Generic[T]):
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise QtUnavailableError("pyside6_unavailable")

    class QtWorkerCoordinator:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise QtUnavailableError("pyside6_unavailable")
else:
    PYSIDE_AVAILABLE = True

    @dataclass(frozen=True, slots=True)
    class WorkerFailure:
        code: str
        summary: str

    class WorkerSignals(QObject):
        started = Signal()
        result = Signal(object)
        error = Signal(object)
        cancelled = Signal()
        finished = Signal()

    class QtTaskRunner(QRunnable, Generic[T]):
        def __init__(self, task: Callable[[CancellationToken], T]) -> None:
            super().__init__()
            self.signals = WorkerSignals()
            self.cancellation = CancellationToken()
            self._task = task

        def cancel(self) -> None:
            self.cancellation.cancel()

        @Slot()
        def run(self) -> None:
            self.signals.started.emit()
            try:
                if self.cancellation.cancelled:
                    raise OperationCancelled("cancelled before worker start")
                result = self._task(self.cancellation)
            except OperationCancelled:
                self.signals.cancelled.emit()
            except Exception as error:  # UI boundary converts exceptions to a bounded structure.
                code = getattr(error, "code", "worker_failed")
                self.signals.error.emit(WorkerFailure(str(code), type(error).__name__))
            else:
                self.signals.result.emit(result)
            finally:
                self.signals.finished.emit()

    class QtWorkerCoordinator:
        def __init__(self, pool: QThreadPool | None = None) -> None:
            self._pool = pool or QThreadPool.globalInstance()
            self._active: dict[str, QtTaskRunner[object]] = {}

        def start(self, host_id: str, runner: QtTaskRunner[object]) -> None:
            if not host_id.strip():
                raise ValueError("host_id must not be blank")
            if host_id in self._active:
                raise RuntimeError("host_workflow_busy")
            self._active[host_id] = runner
            runner.signals.finished.connect(lambda: self._active.pop(host_id, None))
            self._pool.start(runner)

        def cancel(self, host_id: str) -> bool:
            runner = self._active.get(host_id)
            if runner is None:
                return False
            runner.cancel()
            return True

        def is_active(self, host_id: str) -> bool:
            return host_id in self._active


def require_pyside6() -> None:
    if not PYSIDE_AVAILABLE:
        raise QtUnavailableError("pyside6_unavailable")
