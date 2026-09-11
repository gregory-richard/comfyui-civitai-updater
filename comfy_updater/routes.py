from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from aiohttp import web

from .constants import CACHE_SCHEMA_VERSION, SUPPORTED_MODEL_TYPES
from .jobs import MATURE_MODES, _normalize_cached_item_urls
from .path_resolver import normalize_model_types
from .sidecar import read_json, write_json

try:
    from server import PromptServer
except ModuleNotFoundError:  # pragma: no cover - only outside ComfyUI
    PromptServer = None


_ROUTES_REGISTERED = False


def register_routes(config_store, updater_service, job_manager, archive_store) -> None:
    global _ROUTES_REGISTERED
    if _ROUTES_REGISTERED:
        return
    if PromptServer is None or not getattr(PromptServer, "instance", None):
        print("Civitai updater: PromptServer is not available, routes were not registered.")
        return

    routes = PromptServer.instance.routes

    @routes.get("/civitai-updater/config")
    async def get_config(request):  # noqa: ARG001
        config = config_store.get_public()
        return web.json_response(
            {
                "config": config,
                "supportedModelTypes": list(SUPPORTED_MODEL_TYPES),
                "effectiveRoots": updater_service.get_effective_roots(),
            }
        )

    @routes.post("/civitai-updater/config")
    async def save_config(request):
        payload = await _read_json(request)
        incoming = _normalize_config_payload(payload)
        updated = config_store.update(incoming)
        public = dict(updated)
        public["apiKey"] = ""
        public["hasApiKey"] = bool(updated.get("apiKey", "").strip())
        return web.json_response(
            {
                "config": public,
                "effectiveRoots": updater_service.get_effective_roots(),
            }
        )

    @routes.post("/civitai-updater/jobs/scan")
    async def start_scan_job(request):
        payload = await _read_json(request)
        payload = _normalize_job_payload(payload)
        job = job_manager.start(
            "scan",
            lambda progress, item, control: updater_service.run_scan(payload, progress, item, control),
        )
        if not job:
            return web.json_response({"error": "A job is already running."}, status=409)
        return web.json_response({"jobId": job.id})

    @routes.post("/civitai-updater/jobs/check-updates")
    async def start_check_updates_job(request):
        payload = await _read_json(request)
        payload = _normalize_job_payload(payload)

        progress_path = config_store.data_dir / "progress.json"
        cache_path = config_store.data_dir / "last_check.json"
        item_count = 0
        # The runner thread can emit items before job_manager.start() returns,
        # so it reads the job record from this holder instead of a closure
        # variable that may not be assigned yet.
        job_holder: dict = {}

        # Seed the job with the previous check's results so the panel keeps
        # showing them (marked provisional) while models are re-checked. Every
        # cached item is carried, not just the requested types: a check of one
        # type must not make the other types vanish from the panel.
        cache_data = await asyncio.to_thread(read_json, cache_path)
        seed_items = _seed_items_from_cache(cache_data)

        def runner(progress, item_cb, control):
            nonlocal item_count

            def item_cb_with_progress(item):
                nonlocal item_count
                item_cb(item)
                item_count += 1
                job_ref = job_holder.get("job")
                if job_ref is not None and item_count % 5 == 0:
                    _write_progress(progress_path, job_ref)

            summary, items = updater_service.run_check_updates(
                payload, progress, item_cb_with_progress, control,
            )
            # A check of a subset of types replaces only that subset in the
            # cache; the previous results for the other types are kept, so
            # the panel and the file-change detection still cover the whole
            # library.
            items = _merge_check_items(cache_data, items, payload.get("modelTypes"))
            summary = job_manager.summarize_check_items(summary, items)
            summary["total"] = len(items)
            if not control.is_cancelled():
                write_json(cache_path, {
                    "schemaVersion": CACHE_SCHEMA_VERSION,
                    "checkedAt": datetime.now(timezone.utc).isoformat(),
                    "summary": summary,
                    "items": items,
                })
            progress_path.unlink(missing_ok=True)
            return summary, items

        job_ref = job_manager.start("check-updates", runner, seed_items=seed_items)
        if not job_ref:
            return web.json_response({"error": "A job is already running."}, status=409)
        job_holder["job"] = job_ref
        _write_progress(progress_path, job_ref)
        return web.json_response({"jobId": job_ref.id})

    @routes.get("/civitai-updater/last-check")
    async def get_last_check(request):  # noqa: ARG001
        progress_path = config_store.data_dir / "progress.json"
        progress_data = read_json(progress_path)

        active = job_manager.get_active()
        if progress_data and active:
            return web.json_response({
                "sidecarWarnings": active.summary.get("sidecarWarnings", []),
                "data": {
                    "jobId": active.id,
                    "checkedAt": active.startedAt or "",
                    "summary": active.summary,
                    "itemCount": len(active.items),
                    "inProgress": True,
                }
            })

        if progress_data and not active:
            progress_path.unlink(missing_ok=True)

        cache_path = config_store.data_dir / "last_check.json"
        data = read_json(cache_path)
        # The inspection walks every model root on disk — keep it off the
        # server event loop so large libraries don't stall other requests.
        current_paths, sidecar_warnings = await asyncio.to_thread(
            updater_service.inspect_current_files
        )
        if not data:
            return web.json_response({"data": None, "sidecarWarnings": sidecar_warnings})
        if int(data.get("schemaVersion") or 0) != CACHE_SCHEMA_VERSION:
            return web.json_response(
                {"data": None, "cacheInvalid": True, "sidecarWarnings": sidecar_warnings}
            )
        job = job_manager.load_cached_check(data)

        cached_paths = {str(item.get("modelPath", "")).lower() for item in data.get("items", []) if item.get("modelPath")}
        added = len(current_paths - cached_paths)
        removed = len(cached_paths - current_paths)

        return web.json_response({
            "sidecarWarnings": sidecar_warnings,
            "data": {
                "jobId": job.id,
                "checkedAt": data.get("checkedAt", ""),
                "summary": data.get("summary", {}),
                "itemCount": len(data.get("items", [])),
                "inProgress": False,
                "filesChanged": added + removed > 0,
                "filesAdded": added,
                "filesRemoved": removed,
            }
        })

    @routes.get("/civitai-updater/jobs/active")
    async def get_active_job(request):  # noqa: ARG001
        active = job_manager.get_active()
        if not active:
            return web.json_response({"job": None})
        return web.json_response({"job": active.as_dict(include_items=False)})

    @routes.get("/civitai-updater/jobs/{job_id}")
    async def get_job(request):
        job_id = request.match_info.get("job_id", "")
        job = job_manager.get(job_id)
        if not job:
            return web.json_response({"error": "job not found"}, status=404)
        include_items = request.query.get("includeItems", "0").lower() in ("1", "true", "yes")
        return web.json_response(job.as_dict(include_items=include_items))

    @routes.get("/civitai-updater/jobs/{job_id}/items")
    async def get_job_items(request):
        job_id = request.match_info.get("job_id", "")
        offset = _read_int_query(request, "offset", default=0, minimum=0, maximum=10_000_000)
        limit = _read_int_query(request, "limit", default=25, minimum=1, maximum=500)
        mode = request.query.get("mode", "").strip().lower() or None
        if mode not in (None, "updates"):
            return web.json_response({"error": "invalid mode"}, status=400)
        model_types = _read_multi_query(request, "modelType")
        base_models = _read_multi_query(request, "baseModel")
        show_hidden = request.query.get("showHidden", "0").lower() in ("1", "true", "yes")
        sort = request.query.get("sort", "").strip().lower() or None
        group_by = request.query.get("groupBy", "").strip() or None
        then_by = request.query.get("thenBy", "").strip() or None
        collapsed = _read_multi_query(request, "collapsed")
        mature = request.query.get("mature", "").strip().lower()
        if mature not in MATURE_MODES:
            mature = str(config_store.get().get("matureMode") or "show")

        result = job_manager.get_items(
            job_id, offset=offset, limit=limit, mode=mode,
            model_types=model_types, base_models=base_models, sort=sort, show_hidden=show_hidden,
            group_by=group_by, then_by=then_by, mature=mature, collapsed=collapsed,
        )
        if not result:
            return web.json_response({"error": "job not found"}, status=404)

        return web.json_response(
            {
                "jobId": job_id,
                "totalItems": result["total"],
                "offset": result["offset"],
                "limit": result["limit"],
                "mode": mode,
                "facets": result["facets"],
                "groups": result["groups"],
                "grouping": result["grouping"],
                "startsMidPrimary": result["startsMidPrimary"],
                "startsMidSecondary": result["startsMidSecondary"],
                "matureHidden": result["matureHidden"],
                "matureMode": result["matureMode"],
                "items": result["items"],
            }
        )

    @routes.post("/civitai-updater/archived-updates")
    async def archive_updates(request):
        payload = await _read_json(request)
        model_id, version_ids = _normalize_archive_payload(payload)
        if not model_id or not version_ids:
            return web.json_response({"error": "modelId and versionIds are required"}, status=400)
        archived = archive_store.archive(model_id, version_ids)
        return web.json_response({"modelId": model_id, "archivedVersionIds": archived})

    @routes.post("/civitai-updater/archived-updates/restore")
    async def restore_updates(request):
        payload = await _read_json(request)
        model_id, version_ids = _normalize_archive_payload(payload)
        if not model_id or not version_ids:
            return web.json_response({"error": "modelId and versionIds are required"}, status=400)
        archived = archive_store.restore(model_id, version_ids)
        return web.json_response({"modelId": model_id, "archivedVersionIds": archived})

    @routes.post("/civitai-updater/jobs/{job_id}/pause")
    async def pause_job(request):
        job_id = request.match_info.get("job_id", "")
        job = job_manager.pause(job_id)
        if not job:
            return web.json_response({"error": "job not found"}, status=404)
        return web.json_response(job.as_dict(include_items=False))

    @routes.post("/civitai-updater/jobs/{job_id}/resume")
    async def resume_job(request):
        job_id = request.match_info.get("job_id", "")
        job = job_manager.resume(job_id)
        if not job:
            return web.json_response({"error": "job not found"}, status=404)
        return web.json_response(job.as_dict(include_items=False))

    @routes.post("/civitai-updater/jobs/{job_id}/stop")
    async def stop_job(request):
        job_id = request.match_info.get("job_id", "")
        job = job_manager.cancel(job_id)
        if not job:
            return web.json_response({"error": "job not found"}, status=404)
        return web.json_response(job.as_dict(include_items=False))

    _ROUTES_REGISTERED = True
    print("Civitai updater: routes registered")


async def _read_json(request) -> dict:
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        payload = {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _normalize_job_payload(payload: dict) -> dict:
    model_types = normalize_model_types(payload.get("modelTypes"))
    return {
        "modelTypes": model_types,
        "includeCustomPaths": bool(payload.get("includeCustomPaths", True)),
        "refetchMetadata": bool(payload.get("refetchMetadata", False)),
        "forceRehash": bool(payload.get("forceRehash", False)),
    }


def _normalize_config_payload(payload: dict) -> dict:
    incoming = {}

    if "apiKey" in payload:
        key = payload.get("apiKey")
        incoming["apiKey"] = key if isinstance(key, str) else ""

    if "cacheTtlMinutes" in payload:
        incoming["cacheTtlMinutes"] = payload.get("cacheTtlMinutes")
    if "requestTimeoutSeconds" in payload:
        incoming["requestTimeoutSeconds"] = payload.get("requestTimeoutSeconds")
    if "maxRetries" in payload:
        incoming["maxRetries"] = payload.get("maxRetries")
    if "requestDelayMs" in payload:
        incoming["requestDelayMs"] = payload.get("requestDelayMs")
    if "useComfyPaths" in payload:
        incoming["useComfyPaths"] = bool(payload.get("useComfyPaths"))
    if "useExtraModelPaths" in payload:
        incoming["useExtraModelPaths"] = bool(payload.get("useExtraModelPaths"))
    if "useCustomPaths" in payload:
        incoming["useCustomPaths"] = bool(payload.get("useCustomPaths"))
    if "treatSidecarsAsInstalled" in payload:
        incoming["treatSidecarsAsInstalled"] = bool(payload.get("treatSidecarsAsInstalled"))
    if "matureMode" in payload:
        incoming["matureMode"] = payload.get("matureMode")

    if "customPaths" in payload:
        custom = payload.get("customPaths")
        if isinstance(custom, dict):
            # Only normalize the model types the client actually sent —
            # filling in missing types as [] would silently wipe their
            # stored custom paths on every settings sync.
            cleaned = {}
            for model_type in SUPPORTED_MODEL_TYPES:
                if model_type in custom:
                    cleaned[model_type] = _normalize_paths_value(custom[model_type])
            if cleaned:
                incoming["customPaths"] = cleaned

    return incoming


def _normalize_paths_value(entries) -> list[str]:
    if isinstance(entries, str):
        raw_parts = entries.replace(";", "\n").splitlines()
        return [item.strip() for item in raw_parts if item.strip()]
    if isinstance(entries, list):
        return [item.strip() for item in entries if isinstance(item, str) and item.strip()]
    return []


def _cached_check_items(cache_data) -> list[dict]:
    """Return the items of a cached check, or nothing for a missing or outdated cache."""
    if not isinstance(cache_data, dict):
        return []
    if int(cache_data.get("schemaVersion") or 0) != CACHE_SCHEMA_VERSION:
        return []
    return [item for item in cache_data.get("items", []) or [] if isinstance(item, dict)]


def _seed_items_from_cache(cache_data) -> list[dict]:
    """Build provisional seed items from a cached check for a new job.

    Each item is marked ``_seeded`` so the job can replace it once the file is
    re-checked. An empty list is returned for missing or outdated caches.
    """
    seeded: list[dict] = []
    for item in _cached_check_items(cache_data):
        entry = dict(_normalize_cached_item_urls(item))
        entry["_seeded"] = True
        seeded.append(entry)
    return seeded


def _merge_check_items(cache_data, fresh_items: list[dict], model_types: list[str] | None) -> list[dict]:
    """Combine a check of ``model_types`` with the cached results of the rest.

    Items of a checked type come only from the fresh run, so files that were
    deleted drop out; items of any other type are carried over unchanged.
    """
    checked_types = set(model_types or [])
    if not checked_types:
        return list(fresh_items)
    carried = [
        _normalize_cached_item_urls(item)
        for item in _cached_check_items(cache_data)
        if item.get("modelType") not in checked_types
    ]
    return carried + list(fresh_items)


def _write_progress(progress_path, job_ref) -> None:
    try:
        write_json(progress_path, {
            "jobId": job_ref.id,
            "startedAt": job_ref.startedAt or "",
            "progress": job_ref.progress,
            "total": job_ref.total,
        })
    except Exception:  # noqa: BLE001
        pass


def _read_int_query(request, key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(request.query.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _read_multi_query(request, key: str) -> list[str] | None:
    values = [value.strip() for value in request.query.getall(key, []) if value and value.strip()]
    return values if values else None


def _normalize_archive_payload(payload: dict) -> tuple[str, list[str]]:
    model_id = str(payload.get("modelId") or "").strip()
    raw_version_ids = payload.get("versionIds")
    version_ids = []
    if isinstance(raw_version_ids, list):
        normalized = set()
        for version_id in raw_version_ids:
            if version_id is None:
                continue
            cleaned = str(version_id).strip()
            if cleaned:
                normalized.add(cleaned)
        version_ids = sorted(normalized)
    return model_id, version_ids
