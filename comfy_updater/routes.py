from __future__ import annotations

from datetime import datetime, timezone

from aiohttp import web

from .constants import SUPPORTED_MODEL_TYPES
from .path_resolver import normalize_model_types
from .sidecar import read_json, write_json

try:
    from server import PromptServer
except ModuleNotFoundError:  # pragma: no cover - only outside ComfyUI
    PromptServer = None


_ROUTES_REGISTERED = False


def register_routes(config_store, updater_service, job_manager) -> None:
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
        return web.json_response({"jobId": job.id})

    @routes.post("/civitai-updater/jobs/check-updates")
    async def start_check_updates_job(request):
        payload = await _read_json(request)
        payload = _normalize_job_payload(payload)

        progress_path = config_store.data_dir / "progress.json"
        cache_path = config_store.data_dir / "last_check.json"
        item_count = 0

        def runner(progress, item_cb, control):
            nonlocal item_count

            def item_cb_with_progress(item):
                nonlocal item_count
                item_cb(item)
                item_count += 1
                if item_count % 5 == 0:
                    _write_progress(progress_path, accumulated_items=None, job_ref=job_ref)

            summary, items = updater_service.run_check_updates(
                payload, progress, item_cb_with_progress, control,
            )
            if not control.is_cancelled():
                write_json(cache_path, {
                    "checkedAt": datetime.now(timezone.utc).isoformat(),
                    "summary": summary,
                    "items": items,
                })
            progress_path.unlink(missing_ok=True)
            return summary, items

        job_ref = job_manager.start("check-updates", runner)
        _write_progress(progress_path, accumulated_items=None, job_ref=job_ref)
        return web.json_response({"jobId": job_ref.id})

    @routes.get("/civitai-updater/last-check")
    async def get_last_check(request):  # noqa: ARG001
        progress_path = config_store.data_dir / "progress.json"
        progress_data = read_json(progress_path)

        active = job_manager.get_active()
        if progress_data and active:
            return web.json_response({
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
        if not data:
            return web.json_response({"data": None})
        job = job_manager.load_cached_check(data)

        cached_paths = {str(item.get("modelPath", "")).lower() for item in data.get("items", []) if item.get("modelPath")}
        current_paths = updater_service.list_current_file_paths()
        added = len(current_paths - cached_paths)
        removed = len(cached_paths - current_paths)

        return web.json_response({
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
        model_type = request.query.get("modelType", "").strip() or None
        base_model = request.query.get("baseModel", "").strip() or None
        sort = request.query.get("sort", "").strip().lower() or None

        result = job_manager.get_items(
            job_id, offset=offset, limit=limit, mode=mode,
            model_type=model_type, base_model=base_model, sort=sort,
        )
        if not result:
            return web.json_response({"error": "job not found"}, status=404)

        total_items, safe_offset, safe_limit, items, facets = result
        return web.json_response(
            {
                "jobId": job_id,
                "totalItems": total_items,
                "offset": safe_offset,
                "limit": safe_limit,
                "mode": mode,
                "facets": facets,
                "items": items,
            }
        )

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

    if "customPaths" in payload:
        custom = payload.get("customPaths")
        if isinstance(custom, dict):
            cleaned = {}
            for model_type in SUPPORTED_MODEL_TYPES:
                entries = custom.get(model_type, [])
                cleaned[model_type] = _normalize_paths_value(entries)
            incoming["customPaths"] = cleaned

    return incoming


def _normalize_paths_value(entries) -> list[str]:
    if isinstance(entries, str):
        raw_parts = entries.replace(";", "\n").splitlines()
        return [item.strip() for item in raw_parts if item.strip()]
    if isinstance(entries, list):
        return [item.strip() for item in entries if isinstance(item, str) and item.strip()]
    return []


def _write_progress(progress_path, *, accumulated_items, job_ref) -> None:
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
