from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading
import time
import uuid

from .constants import MODEL_PAGE_BASE_URL


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
    def __init__(self, archive_store=None) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self.archive_store = archive_store

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
        model_types: list[str] | None = None,
        base_models: list[str] | None = None,
        sort: str | None = None,
        show_hidden: bool = False,
    ) -> tuple[int, int, int, list[dict], dict] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            items = list(job.items)
            provisional = job.status in ("running", "queued", "paused")

        grouped = _group_items_by_model(
            items,
            archived_versions=self._archived_snapshot(),
            provisional=provisional,
        )

        if mode == "updates":
            grouped = [
                g for g in grouped
                if g.get("hasUpdate") or (show_hidden and g.get("hasHiddenUpdates"))
            ]

        available_types: set[str] = set()
        available_bases: set[str] = set()
        for group in grouped:
            model_type = group.get("modelType", "")
            if model_type:
                available_types.add(model_type)
            for local_version in group.get("localVersions", []):
                base_model = local_version.get("baseModel", "")
                if base_model:
                    available_bases.add(base_model)

        model_type_set = set(model_types or [])
        base_model_set = set(base_models or [])

        if model_types is not None:
            grouped = [g for g in grouped if g.get("modelType", "") in model_type_set]
        if base_models is not None:
            grouped = [
                g for g in grouped
                if any(lv.get("baseModel", "") in base_model_set for lv in g.get("localVersions", []))
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

    def summarize_check_items(self, summary: dict, items: list[dict]) -> dict:
        grouped = _group_items_by_model(items, archived_versions=self._archived_snapshot(), provisional=False)
        with_updates = sum(1 for group in grouped if group.get("hasUpdate"))
        hidden_updates = sum(1 for group in grouped if group.get("hasHiddenUpdates"))
        merged = dict(summary or {})
        merged["withUpdates"] = with_updates
        merged["hiddenUpdates"] = hidden_updates
        return merged

    def get_active(self) -> JobRecord | None:
        with self._lock:
            for job in self._jobs.values():
                if job.status in ("running", "queued", "paused"):
                    return job
        return None

    def load_cached_check(self, cache_data: dict) -> JobRecord:
        items = [_normalize_cached_item_urls(item) for item in cache_data.get("items", []) or []]
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
            job.items = items or job.items
            job.progress = job.total
            if not job.message:
                job.message = "Completed"

    def _archived_snapshot(self) -> dict[str, set[str]]:
        if not self.archive_store:
            return {}
        return self.archive_store.snapshot()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_cached_item_urls(item: dict) -> dict:
    if not isinstance(item, dict):
        return item

    normalized = dict(item)
    for key in ("modelUrl", "versionUrl"):
        normalized[key] = _normalize_civitai_model_page_url(normalized.get(key, ""))

    remote_versions = []
    for version in normalized.get("remoteVersions", []) or []:
        if not isinstance(version, dict):
            remote_versions.append(version)
            continue
        version_copy = dict(version)
        version_copy["versionUrl"] = _normalize_civitai_model_page_url(version_copy.get("versionUrl", ""))
        remote_versions.append(version_copy)
    normalized["remoteVersions"] = remote_versions
    return normalized


def _normalize_civitai_model_page_url(url: str) -> str:
    if not isinstance(url, str) or not url:
        return ""

    legacy_bases = (
        "https://civitai.com/models",
        "http://civitai.com/models",
    )
    for legacy_base in legacy_bases:
        if url.startswith(legacy_base):
            return f"{MODEL_PAGE_BASE_URL}{url[len(legacy_base):]}"
    return url


def _group_items_by_model(
    items: list[dict],
    archived_versions: dict[str, set[str]] | None = None,
    provisional: bool = False,
) -> list[dict]:
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
    archived_versions = archived_versions or {}

    for model_id, members in groups.items():
        result.append(_build_group(model_id, members, archived_versions.get(model_id, set()), provisional))

    for item in ungrouped:
        result.append(_build_ungrouped_item(item, provisional))

    return result


def _build_group(model_id: str, members: list[dict], archived_ids: set[str], provisional: bool) -> dict:
    representative = members[0]
    creator_name = ""
    model_url = ""
    model_name = representative.get("modelName", "") or _filename(representative.get("modelPath", ""))
    model_type = representative.get("modelType", "")
    local_versions: list[dict] = []
    local_keys: set[tuple[str, str]] = set()
    local_version_ids: set[str] = set()
    remote_versions_by_id: dict[str, dict] = {}

    for member in members:
        creator_name = creator_name or member.get("creatorName", "")
        model_url = model_url or member.get("modelUrl", "")
        model_name = model_name or member.get("modelName", "")
        model_type = model_type or member.get("modelType", "")

        local_version_id = str(member.get("localVersionId") or "")
        local_key = (member.get("modelPath", ""), local_version_id)
        if local_key not in local_keys:
            local_keys.add(local_key)
            local_versions.append(
                {
                    "versionId": local_version_id,
                    "versionName": member.get("localVersionName", ""),
                    "baseModel": member.get("baseModel", ""),
                    "publishedAt": member.get("localVersionDate", ""),
                    "modelPath": member.get("modelPath", ""),
                    "previewUrl": member.get("localPreviewUrl", ""),
                    "previewType": member.get("localPreviewType", "image"),
                }
            )
        if local_version_id:
            local_version_ids.add(local_version_id)

        for remote_version in member.get("remoteVersions", []):
            version_id = str(remote_version.get("versionId") or "")
            if not version_id:
                continue
            current = remote_versions_by_id.get(version_id)
            if not current or (remote_version.get("versionDate", "") > current.get("versionDate", "")):
                remote_versions_by_id[version_id] = {
                    "versionId": version_id,
                    "versionName": remote_version.get("versionName", ""),
                    "versionDate": remote_version.get("versionDate", ""),
                    "baseModel": remote_version.get("baseModel", ""),
                    "previewUrl": remote_version.get("previewUrl", ""),
                    "previewType": remote_version.get("previewType", "image"),
                    "versionUrl": remote_version.get("versionUrl", ""),
                    "downloadUrl": remote_version.get("downloadUrl", ""),
                }

    local_versions.sort(
        key=lambda version: (version.get("publishedAt", ""), (version.get("versionName") or "").lower()),
        reverse=True,
    )
    newest_local_date = max((version.get("publishedAt", "") for version in local_versions if version.get("publishedAt")), default="")

    candidates = []
    for remote_version in remote_versions_by_id.values():
        version_id = remote_version.get("versionId", "")
        version_date = remote_version.get("versionDate", "")
        if not version_date or version_id in local_version_ids:
            continue
        if newest_local_date and version_date <= newest_local_date:
            continue
        candidates.append(remote_version)

    candidates.sort(key=lambda version: (version.get("versionDate", ""), version.get("versionName", "").lower()), reverse=True)

    new_versions = [version for version in candidates if version.get("versionId", "") not in archived_ids]
    hidden_versions = [version for version in candidates if version.get("versionId", "") in archived_ids]
    primary_visible = new_versions[0] if new_versions else {}
    primary_any = primary_visible or (hidden_versions[0] if hidden_versions else {})
    local_preview = next((version for version in local_versions if version.get("previewUrl")), {})

    return {
        "modelId": model_id,
        "modelType": model_type,
        "modelName": model_name,
        "creatorName": creator_name,
        "modelUrl": model_url,
        "isProvisional": provisional,
        "hasUpdate": bool(new_versions),
        "hasHiddenUpdates": bool(hidden_versions),
        "hasAnyUpdate": bool(new_versions or hidden_versions),
        "newestLocalVersionDate": newest_local_date,
        "localVersions": local_versions,
        "newVersions": new_versions,
        "hiddenNewVersions": hidden_versions,
        "latestVersionId": primary_visible.get("versionId", ""),
        "latestVersionName": primary_visible.get("versionName", ""),
        "latestBaseModel": primary_visible.get("baseModel", ""),
        "latestVersionDate": primary_visible.get("versionDate", ""),
        "sortVersionDate": primary_any.get("versionDate", ""),
        "previewUrl": primary_any.get("previewUrl") or local_preview.get("previewUrl", ""),
        "previewType": primary_any.get("previewType") or local_preview.get("previewType", "image"),
        "versionUrl": primary_any.get("versionUrl", ""),
        "downloadUrl": primary_any.get("downloadUrl", ""),
    }


def _build_ungrouped_item(item: dict, provisional: bool) -> dict:
    local_versions = [
        {
            "versionId": str(item.get("localVersionId") or ""),
            "versionName": item.get("localVersionName", ""),
            "baseModel": item.get("baseModel", ""),
            "publishedAt": item.get("localVersionDate", ""),
            "modelPath": item.get("modelPath", ""),
            "previewUrl": item.get("localPreviewUrl", ""),
            "previewType": item.get("localPreviewType", "image"),
        }
    ]
    return {
        "modelId": "",
        "modelType": item.get("modelType", ""),
        "modelName": item.get("modelName", "") or _filename(item.get("modelPath", "")),
        "creatorName": item.get("creatorName", ""),
        "modelUrl": item.get("modelUrl", ""),
        "isProvisional": provisional,
        "hasUpdate": False,
        "hasHiddenUpdates": False,
        "hasAnyUpdate": False,
        "newestLocalVersionDate": item.get("localVersionDate", ""),
        "localVersions": local_versions,
        "newVersions": [],
        "hiddenNewVersions": [],
        "latestVersionId": "",
        "latestVersionName": "",
        "latestBaseModel": "",
        "latestVersionDate": "",
        "sortVersionDate": "",
        "previewUrl": item.get("previewUrl", ""),
        "previewType": item.get("previewType", "image"),
        "versionUrl": item.get("versionUrl", ""),
        "downloadUrl": item.get("downloadUrl", ""),
    }


_VALID_SORTS = ("name", "name-desc", "type", "latest-date", "latest-date-desc")


def _sort_grouped(items: list[dict], sort: str | None) -> list[dict]:
    if not sort or sort not in _VALID_SORTS:
        sort = "name"
    if sort == "name":
        return sorted(items, key=lambda group: (group.get("modelName") or "").lower())
    if sort == "name-desc":
        return sorted(items, key=lambda group: (group.get("modelName") or "").lower(), reverse=True)
    if sort == "type":
        return sorted(items, key=lambda group: ((group.get("modelType") or ""), (group.get("modelName") or "").lower()))
    if sort == "latest-date":
        return sorted(items, key=lambda group: group.get("sortVersionDate") or "")
    if sort == "latest-date-desc":
        return sorted(items, key=lambda group: group.get("sortVersionDate") or "", reverse=True)
    return items


def _filename(path: str) -> str:
    index = max(path.rfind("/"), path.rfind("\\"))
    return path[index + 1 :] if index >= 0 else path


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
