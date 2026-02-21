from __future__ import annotations

from datetime import datetime
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
        model = self.get_model(model_id)
        if not model:
            return None
        versions = model.get("modelVersions") or []
        if not versions:
            return None
        versions = sorted(versions, key=_version_sort_key, reverse=True)
        return versions[0]

    def model_page_url(self, model_id: int | str) -> str:
        return f"{MODEL_PAGE_BASE_URL}/{model_id}"

    def version_page_url(self, model_id: int | str, version_id: int | str | None = None) -> str:
        if version_id:
            return f"{MODEL_PAGE_BASE_URL}/{model_id}?modelVersionId={version_id}"
        return self.model_page_url(model_id)

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


def _version_sort_key(version: dict) -> tuple:
    created_at = version.get("createdAt") or version.get("publishedAt") or ""
    try:
        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        created_ts = parsed.timestamp()
    except ValueError:
        created_ts = 0

    version_id = version.get("id") or 0
    try:
        numeric_id = int(version_id)
    except (TypeError, ValueError):
        numeric_id = 0

    return (created_ts, numeric_id)

