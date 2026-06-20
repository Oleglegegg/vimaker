"""Background workers (QThread) that keep the UI responsive.

Two kinds of work run off the UI thread:
  - QueueWorker: processes a list of Jobs sequentially (full pipeline each).
  - TaskWorker: runs a single callable (per-field regeneration) and returns its result.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal

from ..config import load_settings
from ..job import Job, run_full


class QueueWorker(QObject):
    job_started = Signal(int)            # index
    job_progress = Signal(int, str)      # index, stage
    job_done = Signal(int, object)       # index, Job
    all_done = Signal()

    def __init__(self, jobs: list[Job]) -> None:
        super().__init__()
        self.jobs = jobs
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        settings = load_settings()
        for i, job in enumerate(self.jobs):
            if self._stop:
                break
            from ..job import JobStatus
            if job.status == JobStatus.DONE:
                continue
            self.job_started.emit(i)
            run_full(job, settings, progress=lambda m, idx=i: self.job_progress.emit(idx, m))
            self.job_done.emit(i, job)
        self.all_done.emit()


class TaskWorker(QObject):
    progress = Signal(str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable) -> None:
        super().__init__()
        self.fn = fn

    def run(self) -> None:
        try:
            result = self.fn(self.progress.emit)
            self.done.emit(result)
        except Exception as exc:
            import traceback
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")


def run_on_thread(parent, worker: QObject, run_attr: str = "run") -> QThread:
    """Move a worker to a fresh QThread, start it, and auto-clean on completion."""
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(getattr(worker, run_attr))

    # finish signals quit the thread; keep references alive on parent to avoid GC
    for sig_name in ("all_done", "done", "failed"):
        sig = getattr(worker, sig_name, None)
        if sig is not None:
            sig.connect(thread.quit)

    if not hasattr(parent, "_threads"):
        parent._threads = []
    entry = (thread, worker)
    parent._threads.append(entry)

    def _cleanup() -> None:
        # drop our reference so finished workers/threads can be garbage-collected
        try:
            parent._threads.remove(entry)
        except ValueError:
            pass
        worker.deleteLater()
        thread.deleteLater()

    thread.finished.connect(_cleanup)
    thread.start()
    return thread
