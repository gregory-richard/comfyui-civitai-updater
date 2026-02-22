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
        model_type: str | None = None,
        base_model: str | None = None,
        sort: str | None = None,
    ) -> tuple[int, int, int, list[dict], dict] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None

            grouped = _group_items_by_model(job.items)

            if mode == "updates":
                grouped = [g for g in grouped if g.get("hasUpdate")]

            available_types: set[str] = set()
            available_bases: set[str] = set()
            for g in grouped:
                t = g.get("modelType", "")
                if t:
                    available_types.add(t)
                for lv in g.get("localVersions", []):
                    b = lv.get("baseModel", "")
                    if b:
                        available_bases.add(b)

            if model_type:
                grouped = [g for g in grouped if g.get("modelType") == model_type]
            if base_model:
                grouped = [
                    g for g in grouped
                    if any(lv.get("baseModel") == base_model for lv in g.get("localVersions", []))
                ]

            grouped = _sort_grouped(grouped, sort)

            total = len(grouped)
            safe_offset = max(0, min(offset, total))
            safe_limit = max(1, min(limit, 500))
            page = grouped[safe_offset : safe_offset + safe_limit]
            facets = {
                "modelTypes": sorted(available_types),
                "baseModels": sorted(available_bases),
            }
            return (total, safe_offset, safe_limit, page, facets)

    def get_active(self) -> JobRecord | None:
        """Return the first job that is still running, queued, or paused."""
        with self._lock:
            for job in self._jobs.values():
                if job.status in ("running", "queued", "paused"):
                    return job
        return None

    def load_cached_check(self, cache_data: dict) -> JobRecord:
        """Load previously cached check results into a virtual job record."""
        items = cache_data.get("items", [])
        summary = cache_data.get("summary", {})
        checked_at = cache_data.get("checkedAt", "")

        record = JobRecord(
            id="cached",
            type="check-updates",
            status="completed",
            startedAt=checked_at,
            finishedAt=checked_at,
            summary=summary,
            items=items,
            progress=len(items),
            total=len(items),
            message="Cached",
        )
        with self._lock:
            self._jobs["cached"] = record
        return record

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


def _group_items_by_model(items: list[dict]) -> list[dict]:
    """Group raw items by modelId (or modelUrl as fallback for older data)."""
    groups: dict[str, list[dict]] = {}
    ungrouped: list[dict] = []

    for item in items:
        key = str(item.get("modelId") or "")
        if not key:
            key = item.get("modelUrl") or ""
        if not key:
            ungrouped.append(item)
            continue
        groups.setdefault(key, []).append(item)

    result: list[dict] = []

    for mid, members in groups.items():
        representative = members[0]
        creator_name = ""
        latest_id = ""
        latest_name = ""
        latest_base = ""
        latest_date = ""
        preview_url = ""
        preview_type = "image"
        model_url = ""
        version_url = ""
        download_url = ""

        local_versions = []
        has_latest_locally = False

        for m in members:
            cn = m.get("creatorName") or ""
            if cn and not creator_name:
                creator_name = cn
            lid = m.get("latestVersionId") or ""
            if lid:
                latest_id = str(lid)
            ln = m.get("latestVersionName") or ""
            if ln:
                latest_name = ln
            lb = m.get("latestBaseModel") or ""
            if lb:
                latest_base = lb
            ld = m.get("latestVersionDate") or ""
            if ld:
                latest_date = ld
            pu = m.get("previewUrl") or ""
            if pu and not preview_url:
                preview_url = pu
                preview_type = m.get("previewType", "image")
            mu = m.get("modelUrl") or ""
            if mu:
                model_url = mu
            vu = m.get("versionUrl") or ""
            if vu:
                version_url = vu
            du = m.get("downloadUrl") or ""
            if du:
                download_url = du

            local_vid = str(m.get("localVersionId") or "")
            local_versions.append({
                "versionId": local_vid,
                "versionName": m.get("localVersionName", ""),
                "baseModel": m.get("baseModel", ""),
                "publishedAt": m.get("localVersionDate", ""),
                "modelPath": m.get("modelPath", ""),
                "previewUrl": m.get("localPreviewUrl", ""),
                "previewType": m.get("localPreviewType", "image"),
            })
            if latest_id and local_vid == latest_id:
                has_latest_locally = True

        result.append({
            "modelId": mid,
            "modelType": representative.get("modelType", ""),
            "modelName": representative.get("modelName", ""),
            "creatorName": creator_name,
            "hasUpdate": bool(latest_id) and not has_latest_locally,
            "localVersions": local_versions,
            "latestVersionId": latest_id,
            "latestVersionName": latest_name,
            "latestBaseModel": latest_base,
            "latestVersionDate": latest_date,
            "previewUrl": preview_url,
            "previewType": preview_type,
            "modelUrl": model_url,
            "versionUrl": version_url,
            "downloadUrl": download_url,
        })

    for item in ungrouped:
        result.append({
            "modelId": "",
            "modelType": item.get("modelType", ""),
            "modelName": item.get("modelName", "") or _filename(item.get("modelPath", "")),
            "creatorName": item.get("creatorName", ""),
            "hasUpdate": bool(item.get("hasUpdate")),
            "localVersions": [{
                "versionId": str(item.get("localVersionId") or ""),
                "versionName": item.get("localVersionName", ""),
                "baseModel": item.get("baseModel", ""),
                "publishedAt": item.get("localVersionDate", ""),
                "modelPath": item.get("modelPath", ""),
                "previewUrl": item.get("localPreviewUrl", ""),
                "previewType": item.get("localPreviewType", "image"),
            }],
            "latestVersionId": str(item.get("latestVersionId") or ""),
            "latestVersionName": item.get("latestVersionName", ""),
            "latestBaseModel": item.get("latestBaseModel", ""),
            "latestVersionDate": item.get("latestVersionDate", ""),
            "previewUrl": item.get("previewUrl", ""),
            "previewType": item.get("previewType", "image"),
            "modelUrl": item.get("modelUrl", ""),
            "versionUrl": item.get("versionUrl", ""),
            "downloadUrl": item.get("downloadUrl", ""),
        })

    return result


_VALID_SORTS = ("name", "name-desc", "type", "latest-date", "latest-date-desc")


def _sort_grouped(items: list[dict], sort: str | None) -> list[dict]:
    if not sort or sort not in _VALID_SORTS:
        sort = "name"
    if sort == "name":
        return sorted(items, key=lambda g: (g.get("modelName") or "").lower())
    if sort == "name-desc":
        return sorted(items, key=lambda g: (g.get("modelName") or "").lower(), reverse=True)
    if sort == "type":
        return sorted(items, key=lambda g: ((g.get("modelType") or ""), (g.get("modelName") or "").lower()))
    if sort == "latest-date":
        return sorted(items, key=lambda g: g.get("latestVersionDate") or "")
    if sort == "latest-date-desc":
        return sorted(items, key=lambda g: g.get("latestVersionDate") or "", reverse=True)
    return items


def _filename(path: str) -> str:
    i = max(path.rfind("/"), path.rfind("\\"))
    return path[i + 1:] if i >= 0 else path


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
