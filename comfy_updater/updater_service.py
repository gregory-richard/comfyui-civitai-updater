from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Callable

from .civitai_client import CivitaiClient
from .path_resolver import list_model_files, normalize_model_types, resolve_model_roots
from .sidecar import info_sidecar_path, preview_sidecar_path, read_json, write_json
from .hashing import sha256_file

ProgressCallback = Callable[[int, int, str], None]
ItemCallback = Callable[[dict], None]


class UpdaterService:
    def __init__(self, config_store):
        self.config_store = config_store

    def run_scan(
        self,
        payload: dict,
        progress: ProgressCallback,
        item_callback: ItemCallback | None = None,
        control=None,
    ) -> tuple[dict, list[dict]]:
        return self._run(payload, progress, mode="scan", item_callback=item_callback, control=control)

    def run_check_updates(
        self,
        payload: dict,
        progress: ProgressCallback,
        item_callback: ItemCallback | None = None,
        control=None,
    ) -> tuple[dict, list[dict]]:
        return self._run(payload, progress, mode="check", item_callback=item_callback, control=control)

    def get_effective_roots(
        self, model_types: list[str] | None = None, include_custom_paths: bool = True
    ) -> dict[str, list[str]]:
        config = self.config_store.get()
        normalized = normalize_model_types(model_types)
        roots = resolve_model_roots(config, normalized, include_custom_paths=include_custom_paths)
        return {model_type: [str(path) for path in paths] for model_type, paths in roots.items()}

    def list_current_file_paths(self) -> set[str]:
        """Fast filesystem scan — just returns the set of model file paths (no hashing)."""
        config = self.config_store.get()
        model_types = normalize_model_types(None)
        roots = resolve_model_roots(config, model_types, include_custom_paths=True)
        files = list_model_files(roots)
        return {str(f["path"]).lower() for f in files}

    def _run(
        self,
        payload: dict,
        progress: ProgressCallback,
        mode: str,
        item_callback: ItemCallback | None = None,
        control=None,
    ) -> tuple[dict, list[dict]]:
        config = self.config_store.get()
        model_types = normalize_model_types(payload.get("modelTypes"))
        include_custom = bool(payload.get("includeCustomPaths", True))
        refetch_metadata = bool(payload.get("refetchMetadata", False))
        force_rehash = bool(payload.get("forceRehash", False))
        request_delay_seconds = max(0.0, int(config.get("requestDelayMs", 120)) / 1000.0)

        roots = resolve_model_roots(config, model_types, include_custom_paths=include_custom)
        files = _dedupe_model_files(list_model_files(roots))
        total = len(files)

        version_index: dict[str, set[str]] = {}
        if mode == "check":
            for entry in files:
                sidecar = read_json(info_sidecar_path(entry["path"]))
                if sidecar:
                    mid = str(sidecar.get("modelId") or "")
                    vid = str(sidecar.get("id") or "")
                    if mid and vid:
                        version_index.setdefault(mid, set()).add(vid)

        progress(0, total, f"Discovered {total} model files")

        client = CivitaiClient(
            api_key=config.get("apiKey", ""),
            timeout_seconds=int(config.get("requestTimeoutSeconds", 30)),
            max_retries=int(config.get("maxRetries", 4)),
        )

        stats = {
            "total": total,
            "resolved": 0,
            "notFound": 0,
            "withUpdates": 0,
            "skipped": 0,
            "errors": 0,
        }
        items: list[dict] = []

        for index, model_entry in enumerate(files, start=1):
            if control:
                control.wait_if_paused()
                if control.is_cancelled():
                    break

            model_path = model_entry["path"]
            model_type = model_entry["modelType"]
            progress(index - 1, total, f"{mode}: {model_path.name}")

            try:
                item = self._process_one(
                    client=client,
                    model_path=model_path,
                    model_type=model_type,
                    mode=mode,
                    refetch_metadata=refetch_metadata,
                    force_rehash=force_rehash,
                    version_index=version_index,
                )
            except Exception as exc:  # noqa: BLE001 - return per-file errors without killing the whole job
                stats["errors"] += 1
                item = {
                    "modelPath": str(model_path),
                    "modelType": model_type,
                    "modelId": "",
                    "status": "error",
                    "error": str(exc),
                    "hasUpdate": False,
                    "previewUrl": "",
                    "previewType": "image",
                    "lastCheckedAt": _utc_now(),
                }

            if item.get("status") == "ok":
                stats["resolved"] += 1
            if item.get("status") == "not_found":
                stats["notFound"] += 1
            if item.get("status") == "skipped":
                stats["skipped"] += 1
            if item.get("hasUpdate"):
                stats["withUpdates"] += 1

            items.append(item)
            if item_callback:
                item_callback(item)
            progress(index, total, f"Processed {index}/{total}")
            if request_delay_seconds > 0 and item.get("status") != "skipped":
                time.sleep(request_delay_seconds)

        if mode == "scan":
            summary = {
                "mode": mode,
                "total": stats["total"],
                "refreshed": stats["resolved"],
                "skipped": stats["skipped"],
                "notFound": stats["notFound"],
                "errors": stats["errors"],
                "modelTypes": model_types,
                "includeCustomPaths": include_custom,
            }
        else:
            summary = {
                "mode": mode,
                "total": stats["total"],
                "resolved": stats["resolved"],
                "withUpdates": stats["withUpdates"],
                "notFound": stats["notFound"],
                "errors": stats["errors"],
                "modelTypes": model_types,
                "includeCustomPaths": include_custom,
            }
        return summary, items

    def _process_one(
        self,
        client: CivitaiClient,
        model_path: Path,
        model_type: str,
        mode: str,
        refetch_metadata: bool,
        force_rehash: bool,
        version_index: dict[str, set[str]] | None = None,
    ) -> dict:
        info_path = info_sidecar_path(model_path)

        existing_info = read_json(info_path)
        if mode == "scan" and existing_info and not refetch_metadata:
            _skip_url, _skip_type = _first_preview(existing_info)
            return {
                "modelPath": str(model_path),
                "modelType": model_type,
                "modelId": existing_info.get("modelId", ""),
                "modelName": _model_name(existing_info),
                "baseModel": existing_info.get("baseModel", ""),
                "status": "skipped",
                "hasUpdate": False,
                "localHash": "",
                "localVersionId": existing_info.get("id", ""),
                "localVersionName": existing_info.get("name", ""),
                "latestVersionId": "",
                "latestVersionName": "",
                "latestBaseModel": "",
                "previewUrl": _skip_url,
                "previewType": _skip_type,
                "modelUrl": "",
                "versionUrl": "",
                "downloadUrl": "",
                "lastCheckedAt": _utc_now(),
            }

        local_hash = None
        version_data = None
        model_id = None

        can_use_sidecar = (
            mode == "check"
            and not force_rehash
            and existing_info
            and existing_info.get("modelId")
            and existing_info.get("id")
        )

        if can_use_sidecar:
            model_id = existing_info.get("modelId")
            version_data = {
                "id": existing_info.get("id"),
                "name": existing_info.get("name"),
                "baseModel": existing_info.get("baseModel", ""),
                "modelId": model_id,
                "downloadUrl": existing_info.get("downloadUrl"),
                "publishedAt": existing_info.get("publishedAt", ""),
                "model": existing_info.get("model", {}),
                "images": existing_info.get("images", []),
            }
        else:
            local_hash = sha256_file(model_path)
            version_data = client.get_version_by_hash(local_hash)
            if version_data:
                model_id = version_data.get("modelId")

        if not version_data or not model_id:
            payload = {
                "modelPath": str(model_path),
                "modelType": model_type,
                "modelId": "",
                "modelName": "",
                "baseModel": "",
                "status": "not_found",
                "hasUpdate": False,
                "localHash": local_hash or "",
                "lastCheckedAt": _utc_now(),
                "previewUrl": "",
                "previewType": "image",
                "modelUrl": "",
                "versionUrl": "",
                "downloadUrl": "",
            }
            if mode == "scan" and (refetch_metadata or not existing_info):
                write_json(
                    info_path,
                    {
                        "id": "",
                        "modelId": "",
                        "name": model_path.name,
                        "files": [{"hashes": {"SHA256": local_hash or ""}}],
                        "extensions": {"source": "comfy-civitai-updater"},
                    },
                )
            return payload

        if mode == "scan":
            model_url = client.model_page_url(model_id)
            version_url = client.version_page_url(model_id, version_data.get("id"))
            preview_url, preview_type = _first_preview(version_data)

            sidecar_payload = dict(version_data)
            if local_hash:
                _set_sha256_hash(sidecar_payload, local_hash)
            sidecar_payload.setdefault("extensions", {})
            sidecar_payload["extensions"]["source"] = "comfy-civitai-updater"
            sidecar_payload["extensions"]["updatedAt"] = _utc_now()
            if refetch_metadata or not existing_info:
                write_json(info_path, sidecar_payload)

            _download_preview_if_needed(client, model_path, version_data, force=refetch_metadata)

            return {
                "modelPath": str(model_path),
                "modelType": model_type,
                "modelId": str(model_id),
                "modelName": _model_name(version_data),
                "baseModel": version_data.get("baseModel", ""),
                "status": "ok",
                "localHash": local_hash or "",
                "localVersionId": version_data.get("id"),
                "localVersionName": version_data.get("name", ""),
                "latestVersionId": "",
                "latestVersionName": "",
                "latestBaseModel": "",
                "hasUpdate": False,
                "previewUrl": preview_url,
                "previewType": preview_type,
                "modelUrl": model_url,
                "versionUrl": version_url,
                "downloadUrl": "",
                "lastCheckedAt": _utc_now(),
            }

        latest_version = client.get_latest_version_for_model(model_id) or {}
        latest_id = latest_version.get("id")
        local_id = version_data.get("id")
        has_update = bool(latest_id and local_id and str(latest_id) != str(local_id))
        if has_update and version_index and str(latest_id) in version_index.get(str(model_id), set()):
            has_update = False

        creator_name = latest_version.get("_creatorName", "")
        local_name = version_data.get("name", "")
        latest_name = latest_version.get("name", local_name)
        latest_download = _first_download_url(latest_version) or _first_download_url(version_data)
        local_preview_url, local_preview_type = _first_preview(version_data)
        preview_url, preview_type = _first_preview(latest_version)
        if not preview_url:
            preview_url, preview_type = local_preview_url, local_preview_type

        model_url = client.model_page_url(model_id)
        version_url = client.version_page_url(model_id, latest_id or local_id)

        if local_hash and version_data:
            sidecar_payload = dict(version_data)
            _set_sha256_hash(sidecar_payload, local_hash)
            sidecar_payload.setdefault("extensions", {})
            sidecar_payload["extensions"]["source"] = "comfy-civitai-updater"
            sidecar_payload["extensions"]["updatedAt"] = _utc_now()
            write_json(info_path, sidecar_payload)
            _download_preview_if_needed(client, model_path, version_data)

        return {
            "modelPath": str(model_path),
            "modelType": model_type,
            "modelId": str(model_id),
            "modelName": _model_name(version_data),
            "baseModel": version_data.get("baseModel", ""),
            "status": "ok",
            "localHash": local_hash or "",
            "localVersionId": local_id,
            "localVersionName": local_name,
            "localVersionDate": _version_date(version_data),
            "latestVersionId": latest_id,
            "latestVersionName": latest_name,
            "latestBaseModel": latest_version.get("baseModel", ""),
            "latestVersionDate": _version_date(latest_version),
            "hasUpdate": has_update,
            "creatorName": creator_name,
            "previewUrl": preview_url,
            "previewType": preview_type,
            "localPreviewUrl": local_preview_url,
            "localPreviewType": local_preview_type,
            "modelUrl": model_url,
            "versionUrl": version_url,
            "downloadUrl": latest_download or "",
            "lastCheckedAt": _utc_now(),
        }


def _dedupe_model_files(files: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for entry in files:
        path = str(entry["path"]).lower()
        if path in seen:
            continue
        seen.add(path)
        deduped.append(entry)
    return deduped


def _version_date(version_data: dict) -> str:
    for key in ("publishedAt", "createdAt"):
        value = version_data.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _model_name(version_data: dict) -> str:
    model = version_data.get("model")
    if isinstance(model, dict):
        name = model.get("name")
        if isinstance(name, str) and name:
            return name
    return ""


def _first_download_url(version_data: dict) -> str | None:
    direct_url = version_data.get("downloadUrl")
    if isinstance(direct_url, str) and direct_url:
        return direct_url

    files = version_data.get("files") or []
    for file_info in files:
        url = file_info.get("downloadUrl")
        if isinstance(url, str) and url:
            return url
    return None


def _first_preview_url(version_data: dict) -> str | None:
    """Image-only preview URL (used for downloading sidecar thumbnails)."""
    images = version_data.get("images") or []
    for image in images:
        if not isinstance(image, dict):
            continue
        if image.get("type") != "image":
            continue
        url = image.get("url")
        if isinstance(url, str) and url:
            return url
    return None


def _first_preview(version_data: dict) -> tuple[str, str]:
    """Return (url, media_type) preferring images, falling back to video."""
    images = version_data.get("images") or []
    for preferred in ("image", "video"):
        for entry in images:
            if not isinstance(entry, dict) or entry.get("type") != preferred:
                continue
            url = entry.get("url")
            if isinstance(url, str) and url:
                return url, preferred
    return "", "image"


def _set_sha256_hash(version_data: dict, sha256_hash: str) -> None:
    files = version_data.get("files")
    if not isinstance(files, list) or not files:
        return
    first_file = files[0]
    if not isinstance(first_file, dict):
        return
    hashes = first_file.get("hashes")
    if not isinstance(hashes, dict):
        hashes = {}
    hashes["SHA256"] = sha256_hash
    first_file["hashes"] = hashes


def _download_preview_if_needed(
    client: CivitaiClient,
    model_path: Path,
    version_data: dict,
    force: bool = False,
) -> None:
    preview_url = _first_preview_url(version_data)
    if not preview_url:
        return
    preview_path = preview_sidecar_path(model_path)
    if not force and preview_path.exists():
        return
    client.download_file(preview_url, preview_path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
