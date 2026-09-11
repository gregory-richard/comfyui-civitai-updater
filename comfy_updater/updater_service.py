from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Callable

from .civitai_client import CivitaiClient, CivitaiRequestError
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
        paths, _warnings = self.inspect_current_files()
        return paths

    def inspect_current_files(self) -> tuple[set[str], list[dict]]:
        """Return current model paths and non-fatal sidecar discovery warnings."""
        config = self.config_store.get()
        model_types = normalize_model_types(None)
        roots = resolve_model_roots(config, model_types, include_custom_paths=True)
        sidecar_warnings: list[dict] = []
        files = list_model_files(
            roots,
            include_sidecar_only=bool(config.get("treatSidecarsAsInstalled", True)),
            sidecar_warnings=sidecar_warnings,
        )
        return {str(f["path"]).lower() for f in files}, sidecar_warnings

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
        sidecar_warnings: list[dict] = []
        files = _dedupe_model_files(
            list_model_files(
                roots,
                include_sidecar_only=bool(config.get("treatSidecarsAsInstalled", True)),
                sidecar_warnings=sidecar_warnings,
            )
        )
        total = len(files)

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
            info_path = model_entry.get("infoPath")
            preview_path = model_entry.get("previewPath")
            metadata_only = bool(model_entry.get("metadataOnly"))
            progress(index - 1, total, f"{mode}: {model_path.name}")

            try:
                item = self._process_one(
                    client=client,
                    model_path=model_path,
                    model_type=model_type,
                    mode=mode,
                    refetch_metadata=refetch_metadata,
                    force_rehash=force_rehash,
                    info_path=info_path,
                    preview_path=preview_path,
                    metadata_only=metadata_only,
                )
            except Exception as exc:  # noqa: BLE001 - return per-file errors without killing the whole job
                item = {
                    "modelPath": str(model_path),
                    "modelType": model_type,
                    "metadataOnly": metadata_only,
                    "modelId": "",
                    "status": "error",
                    "error": str(exc),
                    "hasUpdate": False,
                    "previewUrl": "",
                    "previewType": "image",
                    "nsfw": False,
                    "lastCheckedAt": _utc_now(),
                }

            if item.get("status") == "ok":
                stats["resolved"] += 1
            if item.get("status") == "not_found":
                stats["notFound"] += 1
            if item.get("status") == "skipped":
                stats["skipped"] += 1
            if item.get("status") == "error":
                stats["errors"] += 1
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
                "sidecarWarnings": sidecar_warnings,
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
                "sidecarWarnings": sidecar_warnings,
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
        info_path: Path | None = None,
        preview_path: Path | None = None,
        metadata_only: bool = False,
    ) -> dict:
        info_path = info_path or info_sidecar_path(model_path)
        preview_path = preview_path or preview_sidecar_path(model_path)

        existing_info = read_json(info_path)
        # A sidecar identifies a model only when it carries both ids. The stub
        # written for a not_found file records the hash but no identity, so it
        # must not count as "metadata already fetched".
        has_identity = _sidecar_identifies_model(existing_info)
        stored_hash = _stored_sha256(existing_info)

        if mode == "scan" and has_identity and not refetch_metadata:
            _download_preview_if_needed(client, preview_path, existing_info, force=False)
            _skip_url, _skip_type = _first_preview(existing_info)
            is_nsfw = False
            if isinstance(existing_info, dict):
                is_nsfw = bool(existing_info.get("nsfw"))
                if not is_nsfw:
                    model_info = existing_info.get("model")
                    if isinstance(model_info, dict):
                        is_nsfw = bool(model_info.get("nsfw"))
            return {
                "modelPath": str(model_path),
                "modelType": model_type,
                "metadataOnly": metadata_only,
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
                "latestVersionDate": "",
                "previewUrl": _skip_url,
                "previewType": _skip_type,
                "remoteVersions": [],
                "modelUrl": "",
                "versionUrl": "",
                "downloadUrl": "",
                "nsfw": is_nsfw,
                "lastCheckedAt": _utc_now(),
            }

        local_hash = None
        version_data = None
        model_id = None

        can_use_sidecar = mode == "check" and has_identity and (metadata_only or not force_rehash)
        can_refetch_by_sidecar_id = (
            mode == "scan" and refetch_metadata and has_identity and (metadata_only or not force_rehash)
        )

        def identify_by_hash() -> tuple[str, dict | None]:
            # A stub sidecar already holds the file's hash: reuse it so a model
            # Civitai did not know last time is retried with one API call
            # instead of re-hashing gigabytes. Force rehash bypasses this.
            file_hash = stored_hash if (stored_hash and not force_rehash) else sha256_file(model_path)
            return file_hash, client.get_version_by_hash(file_hash)

        if can_use_sidecar:
            model_id = existing_info.get("modelId")
            version_data = {
                "id": existing_info.get("id"),
                "name": existing_info.get("name"),
                "baseModel": existing_info.get("baseModel", ""),
                "modelId": model_id,
                "downloadUrl": existing_info.get("downloadUrl"),
                "publishedAt": existing_info.get("publishedAt", ""),
                "createdAt": existing_info.get("createdAt", ""),
                "model": existing_info.get("model", {}),
                "images": existing_info.get("images", []),
            }
            _download_preview_if_needed(client, preview_path, version_data, force=False)
        elif can_refetch_by_sidecar_id:
            model_id = existing_info.get("modelId")
            version_data = client.get_version(existing_info.get("id"))
            if version_data:
                model_id = version_data.get("modelId") or model_id
            else:
                # Fallback when the sidecar version id is stale or unavailable.
                if not metadata_only:
                    local_hash, version_data = identify_by_hash()
                    if version_data:
                        model_id = version_data.get("modelId")
        else:
            if not metadata_only:
                local_hash, version_data = identify_by_hash()
                if version_data:
                    model_id = version_data.get("modelId")

        if not version_data or not model_id:
            payload = {
                "modelPath": str(model_path),
                "modelType": model_type,
                "metadataOnly": metadata_only,
                "modelId": "",
                "modelName": "",
                "baseModel": "",
                "status": "not_found",
                "hasUpdate": False,
                "localHash": local_hash or "",
                "lastCheckedAt": _utc_now(),
                "previewUrl": "",
                "previewType": "image",
                "remoteVersions": [],
                "modelUrl": "",
                "versionUrl": "",
                "downloadUrl": "",
                "nsfw": False,
            }
            if mode == "scan" and not metadata_only and (refetch_metadata or not has_identity):
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
            is_nsfw = False
            if isinstance(version_data, dict):
                model_info = version_data.get("model")
                if isinstance(model_info, dict):
                    is_nsfw = bool(model_info.get("nsfw"))

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

            _download_preview_if_needed(client, preview_path, version_data, force=False)

            return {
                "modelPath": str(model_path),
                "modelType": model_type,
                "metadataOnly": metadata_only,
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
                "latestVersionDate": "",
                "hasUpdate": False,
                "previewUrl": preview_url,
                "previewType": preview_type,
                "remoteVersions": [],
                "modelUrl": model_url,
                "versionUrl": version_url,
                "downloadUrl": "",
                "nsfw": is_nsfw,
                "lastCheckedAt": _utc_now(),
            }

        try:
            creator_name, model_versions, is_nsfw = client.get_model_versions_for_model(model_id)
        except CivitaiRequestError as exc:
            local_preview_url, local_preview_type = _first_preview(version_data)
            return {
                "modelPath": str(model_path),
                "modelType": model_type,
                "metadataOnly": metadata_only,
                "modelId": str(model_id),
                "modelName": _model_name(version_data),
                "baseModel": version_data.get("baseModel", ""),
                "status": "error",
                "error": str(exc),
                "hasUpdate": False,
                "localHash": local_hash or "",
                "localVersionId": version_data.get("id", ""),
                "localVersionName": version_data.get("name", ""),
                "localVersionDate": _version_date(version_data),
                "latestVersionId": "",
                "latestVersionName": "",
                "latestBaseModel": "",
                "latestVersionDate": "",
                "creatorName": "",
                "previewUrl": local_preview_url,
                "previewType": local_preview_type,
                "localPreviewUrl": local_preview_url,
                "localPreviewType": local_preview_type,
                "remoteVersions": [],
                "modelUrl": client.model_page_url(model_id),
                "versionUrl": client.version_page_url(model_id, version_data.get("id")),
                "downloadUrl": "",
                "nsfw": False,
                "lastCheckedAt": _utc_now(),
            }
        remote_versions = _normalize_remote_versions(client, model_id, model_versions)
        local_id = str(version_data.get("id") or "")
        local_date = _version_date(version_data)
        local_remote = next(
            (entry for entry in remote_versions if entry.get("versionId") == local_id),
            None,
        )
        # Sidecars written by other tools may carry no release date. Without
        # one, nothing can be judged newer, so take the date Civitai reports
        # for the very same version.
        if not local_date and local_remote and local_remote.get("versionDate"):
            local_date = local_remote["versionDate"]
            version_data = dict(version_data)
            version_data["publishedAt"] = local_date
        new_versions = [
            remote_version
            for remote_version in remote_versions
            if remote_version.get("versionDate")
            and remote_version.get("versionId", "") != local_id
            and local_date
            and remote_version.get("versionDate", "") > local_date
        ]
        primary_new_version = new_versions[0] if new_versions else {}
        local_name = version_data.get("name", "")
        local_preview_url, local_preview_type = _first_preview(version_data)
        # Sidecars written while the API was SFW-filtered often carry empty
        # image lists. Backfill the local preview from the freshly fetched
        # remote data for the same version so those models heal on re-check.
        if not local_preview_url and local_id:
            if local_remote and local_remote.get("previewUrl"):
                local_preview_url = local_remote["previewUrl"]
                local_preview_type = local_remote.get("previewType") or "image"
                if not preview_path.exists():
                    _download_preview_media(client, preview_path, local_preview_url, local_preview_type)
        # Pick url and type as a pair so a local video preview keeps its
        # "video" type instead of inheriting the empty remote entry's default.
        if primary_new_version.get("previewUrl"):
            preview_url = primary_new_version.get("previewUrl", "")
            preview_type = primary_new_version.get("previewType") or "image"
        else:
            preview_url = local_preview_url
            preview_type = local_preview_type

        model_url = client.model_page_url(model_id)
        version_url = primary_new_version.get("versionUrl", "") or client.version_page_url(model_id, local_id)

        if local_hash and version_data:
            sidecar_payload = dict(version_data)
            _set_sha256_hash(sidecar_payload, local_hash)
            sidecar_payload.setdefault("extensions", {})
            sidecar_payload["extensions"]["source"] = "comfy-civitai-updater"
            sidecar_payload["extensions"]["updatedAt"] = _utc_now()
            write_json(info_path, sidecar_payload)
            _download_preview_if_needed(client, preview_path, version_data)

        return {
            "modelPath": str(model_path),
            "modelType": model_type,
            "metadataOnly": metadata_only,
            "modelId": str(model_id),
            "modelName": _model_name(version_data),
            "baseModel": version_data.get("baseModel", ""),
            "status": "ok",
            "localHash": local_hash or "",
            "localVersionId": local_id,
            "localVersionName": local_name,
            "localVersionDate": local_date,
            "latestVersionId": primary_new_version.get("versionId", ""),
            "latestVersionName": primary_new_version.get("versionName", ""),
            "latestBaseModel": primary_new_version.get("baseModel", ""),
            "latestVersionDate": primary_new_version.get("versionDate", ""),
            "hasUpdate": bool(new_versions),
            "creatorName": creator_name,
            "previewUrl": preview_url,
            "previewType": preview_type,
            "localPreviewUrl": local_preview_url,
            "localPreviewType": local_preview_type,
            "remoteVersions": remote_versions,
            "modelUrl": model_url,
            "versionUrl": version_url,
            "downloadUrl": primary_new_version.get("downloadUrl", ""),
            "nsfw": is_nsfw,
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


def _normalize_remote_versions(
    client: CivitaiClient,
    model_id: int | str,
    model_versions: list[dict] | None,
) -> list[dict]:
    normalized = []
    for version_data in model_versions or []:
        version_id = str(version_data.get("id") or "")
        version_date = _version_date(version_data)
        if not version_id or not version_date:
            continue
        preview_url, preview_type = _first_preview(version_data)
        normalized.append(
            {
                "versionId": version_id,
                "versionName": version_data.get("name", ""),
                "versionDate": version_date,
                "baseModel": version_data.get("baseModel", ""),
                "previewUrl": preview_url,
                "previewType": preview_type,
                "versionUrl": client.version_page_url(model_id, version_id),
                "downloadUrl": _first_download_url(version_data) or "",
                "availability": _version_availability(version_data),
            }
        )
    normalized.sort(
        key=lambda version: (version.get("versionDate", ""), version.get("versionName", "").lower()),
        reverse=True,
    )
    return normalized


def _version_availability(version_data: dict) -> str:
    availability = version_data.get("availability")
    return availability if isinstance(availability, str) else ""


def _sidecar_identifies_model(info: dict | None) -> bool:
    if not isinstance(info, dict):
        return False
    return bool(info.get("modelId")) and bool(info.get("id"))


def _stored_sha256(info: dict | None) -> str:
    """Return the SHA256 recorded in a sidecar's first file entry, if any."""
    if not isinstance(info, dict):
        return ""
    files = info.get("files")
    if not isinstance(files, list) or not files or not isinstance(files[0], dict):
        return ""
    hashes = files[0].get("hashes")
    if not isinstance(hashes, dict):
        return ""
    value = hashes.get("SHA256") or hashes.get("sha256") or ""
    return value.strip().lower() if isinstance(value, str) else ""


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
    preview_path: Path,
    version_data: dict,
    force: bool = False,
) -> None:
    preview_url, preview_type = _first_preview(version_data)
    if not preview_url:
        return
    if not force and preview_path.exists():
        return
    _download_preview_media(client, preview_path, preview_url, preview_type)


def _download_preview_media(
    client: CivitaiClient,
    preview_path: Path,
    preview_url: str,
    preview_type: str,
) -> None:
    if preview_type == "video":
        client.download_video_first_frame_as_png(preview_url, preview_path)
        return
    client.download_image_as_png(preview_url, preview_path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
