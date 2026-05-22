from __future__ import annotations

import io
from pathlib import Path
import shutil
import subprocess
import time
import requests

from .constants import MODEL_BY_ID_URL, MODEL_PAGE_BASE_URL, MODEL_VERSION_BY_ID_URL, VERSION_BY_HASH_URL

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional import guard
    Image = None


class CivitaiClient:
    def __init__(self, api_key: str, timeout_seconds: int, max_retries: int, civitai_domain: str = "civitai.red"):
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.civitai_domain = "civitai.red"
        self.session = requests.Session()
        self._model_cache: dict[str, dict | None] = {}
        self.default_headers = {
            "User-Agent": "comfyui-civitai-updater/0.1",
        }
        api_key = (api_key or "").strip()
        if api_key:
            self.default_headers["Authorization"] = f"Bearer {api_key}"

    def get_version_by_hash(self, sha256_hash: str) -> dict | None:
        return self._get_json(f"{VERSION_BY_HASH_URL}/{sha256_hash}")

    def get_model(self, model_id: int | str) -> dict | None:
        key = str(model_id)
        if key not in self._model_cache:
            self._model_cache[key] = self._get_json(f"{MODEL_BY_ID_URL}/{model_id}")
        return self._model_cache[key]

    def get_version(self, version_id: int | str) -> dict | None:
        return self._get_json(f"{MODEL_VERSION_BY_ID_URL}/{version_id}")

    def get_model_versions_for_model(self, model_id: int | str) -> tuple[str, list[dict], bool]:
        model = self.get_model(model_id)
        if not model:
            return ("", [], False)
        versions = model.get("modelVersions") or []
        creator = model.get("creator")
        creator_name = ""
        if isinstance(creator, dict):
            creator_name = creator.get("username") or ""
        is_nsfw = bool(model.get("nsfw"))
        return (creator_name, versions, is_nsfw)

    def model_page_url(self, model_id: int | str, nsfw: bool = False) -> str:
        return f"https://civitai.red/models/{model_id}"

    def version_page_url(self, model_id: int | str, version_id: int | str | None = None, nsfw: bool = False) -> str:
        if version_id:
            return f"https://civitai.red/models/{model_id}?modelVersionId={version_id}"
        return self.model_page_url(model_id, nsfw=nsfw)

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

    def download_image_as_png(self, url: str, target_path: Path, max_bytes: int = 10_000_000) -> bool:
        """Download an image URL and save it as a PNG file."""
        data = self._download_bytes(url, max_bytes=max_bytes)
        if not data:
            return False

        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.with_suffix(f"{target_path.suffix}.tmp")
        try:
            if Image is None:
                if not _is_png_data(data):
                    return False
                with tmp_path.open("wb") as fh:
                    fh.write(data)
                tmp_path.replace(target_path)
                return True

            with Image.open(io.BytesIO(data)) as image:
                if image.mode not in ("RGB", "RGBA"):
                    has_alpha = "A" in image.getbands()
                    image = image.convert("RGBA" if has_alpha else "RGB")
                image.save(tmp_path, format="PNG")
            tmp_path.replace(target_path)
            return True
        except Exception:  # noqa: BLE001
            tmp_path.unlink(missing_ok=True)
            return False

    def download_video_first_frame_as_png(
        self,
        url: str,
        target_path: Path,
        max_bytes: int = 25_000_000,
    ) -> bool:
        """Download a video URL and extract its first frame to PNG via ffmpeg."""
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            return False

        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_video = target_path.with_suffix(".preview_video.tmp.mp4")
        tmp_png = target_path.with_suffix(".preview_frame.tmp.png")

        if not self.download_file(url, tmp_video, max_bytes=max_bytes):
            return False

        try:
            process = subprocess.run(  # noqa: S603
                [
                    ffmpeg_path,
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(tmp_video),
                    "-frames:v",
                    "1",
                    str(tmp_png),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if process.returncode != 0 or not tmp_png.exists() or tmp_png.stat().st_size == 0:
                tmp_png.unlink(missing_ok=True)
                return False
            tmp_png.replace(target_path)
            return True
        except Exception:  # noqa: BLE001
            tmp_png.unlink(missing_ok=True)
            return False
        finally:
            tmp_video.unlink(missing_ok=True)

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
                if response.status_code in (401, 403):
                    print(f"Civitai API Key validation failed: {response.status_code} {response.reason}. Please verify your API Key in the settings panel.")
                    return None
                if response.status_code in (400, 404):
                    return None
                last_error = f"{response.status_code} {response.reason}"

            if attempt < self.max_retries:
                time.sleep(_retry_delay_seconds(attempt))

        if last_error:
            print(f"Civitai updater request failed: {url} :: {last_error}")
        return None

    def _download_bytes(self, url: str, max_bytes: int) -> bytes | None:
        try:
            response = self.session.get(
                url,
                timeout=self.timeout_seconds,
                headers=self.default_headers,
                stream=True,
            )
            if not response.ok:
                return None
            chunks: list[bytes] = []
            written = 0
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                written += len(chunk)
                if written > max_bytes:
                    return None
                chunks.append(chunk)
            return b"".join(chunks)
        except Exception:  # noqa: BLE001
            return None


def _retry_delay_seconds(attempt: int) -> float:
    return min(10.0, 0.5 * (2**attempt))


def _is_png_data(data: bytes) -> bool:
    return data.startswith(b"\x89PNG\r\n\x1a\n")

