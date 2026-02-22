from __future__ import annotations

from pathlib import Path
import time
import requests

from .constants import MODEL_BY_ID_URL, MODEL_PAGE_BASE_URL, MODEL_VERSION_BY_ID_URL, VERSION_BY_HASH_URL


class CivitaiClient:
    def __init__(self, api_key: str, timeout_seconds: int, max_retries: int):
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.session = requests.Session()
        self.default_headers = {
            "User-Agent": "comfyui-civitai-updater/0.1",
        }
        api_key = (api_key or "").strip()
        if api_key:
            self.default_headers["Authorization"] = f"Bearer {api_key}"

    def get_version_by_hash(self, sha256_hash: str) -> dict | None:
        return self._get_json(f"{VERSION_BY_HASH_URL}/{sha256_hash}")

    def get_model(self, model_id: int | str) -> dict | None:
        return self._get_json(f"{MODEL_BY_ID_URL}/{model_id}")

    def get_version(self, version_id: int | str) -> dict | None:
        return self._get_json(f"{MODEL_VERSION_BY_ID_URL}/{version_id}")

    def get_latest_version_for_model(self, model_id: int | str) -> dict | None:
        """Return the primary version as determined by Civitai (first in the array).

        The API returns modelVersions ordered by the creator's chosen `index`,
        not by date. Sorting by createdAt would override the creator's intent —
        e.g. a Wan Video variant added after the main Flux version would wrongly
        appear as the "latest".
        """
        model = self.get_model(model_id)
        if not model:
            return None
        versions = model.get("modelVersions") or []
        if not versions:
            return None
        latest = versions[0]
        creator = model.get("creator")
        if isinstance(creator, dict):
            latest["_creatorName"] = creator.get("username") or ""
        return latest

    def model_page_url(self, model_id: int | str) -> str:
        return f"{MODEL_PAGE_BASE_URL}/{model_id}"

    def version_page_url(self, model_id: int | str, version_id: int | str | None = None) -> str:
        if version_id:
            return f"{MODEL_PAGE_BASE_URL}/{model_id}?modelVersionId={version_id}"
        return self.model_page_url(model_id)

    def download_file(self, url: str, target_path: Path, max_bytes: int = 10_000_000) -> bool:
        """Download a file (e.g. preview image) to *target_path*. Returns True on success."""
        try:
            response = self.session.get(
                url, timeout=self.timeout_seconds, headers=self.default_headers, stream=True
            )
            if not response.ok:
                return False
            target_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = target_path.with_suffix(f"{target_path.suffix}.tmp")
            written = 0
            with tmp_path.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=8192):
                    written += len(chunk)
                    if written > max_bytes:
                        tmp_path.unlink(missing_ok=True)
                        return False
                    fh.write(chunk)
            tmp_path.replace(target_path)
            return True
        except Exception:  # noqa: BLE001
            if target_path.with_suffix(f"{target_path.suffix}.tmp").exists():
                target_path.with_suffix(f"{target_path.suffix}.tmp").unlink(missing_ok=True)
            return False

    def _get_json(self, url: str) -> dict | None:
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    timeout=self.timeout_seconds,
                    headers=self.default_headers,
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                response = None
            else:
                if response.ok:
                    try:
                        return response.json()
                    except ValueError:
                        return None
                if response.status_code in (400, 401, 403, 404):
                    return None
                last_error = f"{response.status_code} {response.reason}"

            if attempt < self.max_retries:
                time.sleep(_retry_delay_seconds(attempt))

        if last_error:
            print(f"Civitai updater request failed: {url} :: {last_error}")
        return None


def _retry_delay_seconds(attempt: int) -> float:
    return min(10.0, 0.5 * (2**attempt))

