from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading
import time
import uuid


@dataclass
class JobRecord:
    id: str
    type: str
    status: str = "queued"
    startedAt: str | None = None
    finishedAt: str | None = None
    progress: int = 0
    total: int = 0
    message: str = ""
    summary: dict = field(default_factory=dict)
    items: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    control: "JobControl | None" = None

    def as_dict(self, include_items: bool = True) -> dict:
        payload = {
            "jobId": self.id,
            "type": self.type,
            "status": self.status,
            "startedAt": self.startedAt,
            "finishedAt": self.finishedAt,
            "progress": self.progress,
            "total": self.total,
            "message": self.message,
            "summary": self.summary,
            "itemCount": len(self.items),
            "errors": self.errors,
        }
        if include_items:
            payload["items"] = self.items
        return payload


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def start(self, job_type: str, runner) -> JobRecord:
        job_id = str(uuid.uuid4())
        control = JobControl()
        record = JobRecord(id=job_id, type=job_type, control=control)
        with self._lock:
            self._jobs[job_id] = record

        thread = threading.Thread(
            target=self._run_job,
            args=(record, runner, control),
            daemon=True,
            name=f"civitai-updater-{job_type}-{job_id[:8]}",
        )
        thread.start()
        return record

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def get_items(
        self,
        job_id: str,
        offset: int = 0,
        limit: int = 25,
        mode: str | None = None,
    ) -> tuple[int, int, int, list[dict]] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None

            items = job.items
            if mode == "updates":
                items = [item for item in items if bool(item.get("hasUpdate"))]

            total = len(items)
            safe_offset = max(0, min(offset, total))
            safe_limit = max(1, min(limit, 500))
            page = items[safe_offset : safe_offset + safe_limit]
            return (total, safe_offset, safe_limit, page)

    def pause(self, job_id: str) -> JobRecord | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status != "running" or not job.control:
                return job
            job.control.pause()
            job.status = "paused"
            job.message = "Paused"
            return job

    def resume(self, job_id: str) -> JobRecord | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status != "paused" or not job.control:
                return job
            job.control.resume()
            job.status = "running"
            job.message = "Resumed"
            return job

    def cancel(self, job_id: str) -> JobRecord | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status in ("completed", "failed", "cancelled"):
                return job
            if job.control:
                job.control.cancel()
            if job.status == "queued":
                job.status = "cancelled"
                job.finishedAt = _utc_now()
                job.message = "Cancelled"
            return job

    def _run_job(self, job: JobRecord, runner, control: "JobControl") -> None:
        with self._lock:
            job.status = "running"
            job.startedAt = _utc_now()

        def progress(current: int, total: int, message: str) -> None:
            with self._lock:
                if job.status == "paused":
                    # Keep explicit paused state while still allowing progress data to update.
                    pass
                job.progress = max(0, int(current))
                job.total = max(0, int(total))
                job.message = message or ""

        def emit_item(item: dict) -> None:
            with self._lock:
                job.items.append(item)

        try:
            summary, items = runner(progress, emit_item, control)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                if control.is_cancelled():
                    job.status = "cancelled"
                    job.finishedAt = _utc_now()
                    job.message = "Cancelled"
                    return
                job.status = "failed"
                job.finishedAt = _utc_now()
                job.errors.append(str(exc))
            return

        with self._lock:
            if control.is_cancelled():
                job.status = "cancelled"
                job.message = "Cancelled"
            else:
                job.status = "completed"
            job.finishedAt = _utc_now()
            job.summary = summary or {}
            # Keep streamed items while running, but synchronize with final
            # result for consistency in case of backend-side transformations.
            job.items = items or job.items
            job.progress = job.total
            if not job.message:
                job.message = "Completed"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobControl:
    def __init__(self) -> None:
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()
        self._pause_event.clear()

    def pause(self) -> None:
        if not self._cancel_event.is_set():
            self._pause_event.set()

    def resume(self) -> None:
        self._pause_event.clear()

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def wait_if_paused(self) -> None:
        while self._pause_event.is_set() and not self._cancel_event.is_set():
            time.sleep(0.1)
