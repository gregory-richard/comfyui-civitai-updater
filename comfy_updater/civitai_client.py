from __future__ import annotations

import io
from pathlib import Path
import shutil
import subprocess
import time
import requests

from .constants import (
    MODEL_BY_ID_URL,
    MODEL_PAGE_BASE_URL,
    MODEL_VERSION_BY_ID_URL,
    USER_AGENT,
    VERSION_BY_HASH_URL,
)

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional import guard
    Image = None


class CivitaiClient:
    def __init__(self, api_key: str, timeout_seconds: int, max_retries: int):
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.session = requests.Session()
        # Caches the model payload, None for a silent miss, or the error that
        # a strict lookup raised, so several files of one model share a call.
        self._model_cache: dict[str, dict | None | CivitaiRequestError] = {}
        self.default_headers = {
            "User-Agent": USER_AGENT,
        }
        api_key = (api_key or "").strip()
        if api_key:
            self.default_headers["Authorization"] = f"Bearer {api_key}"

    def get_version_by_hash(self, sha256_hash: str) -> dict | None:
        return self._get_json(f"{VERSION_BY_HASH_URL}/{sha256_hash}")

    def get_model(self, model_id: int | str, *, raise_on_error: bool = False) -> dict | None:
        """Fetch a model page payload.

        With ``raise_on_error`` a request that fails after retries, or that
        Civitai refuses (401/403) or cannot find (404), raises
        ``CivitaiRequestError`` instead of returning None, so callers can tell
        a missing model from an empty one.
        """
        key = str(model_id)
        if key not in self._model_cache:
            try:
                self._model_cache[key] = self._get_json(f"{MODEL_BY_ID_URL}/{model_id}", raise_on_error=raise_on_error)
            except CivitaiRequestError as exc:
                self._model_cache[key] = exc
                raise
        cached = self._model_cache[key]
        if isinstance(cached, CivitaiRequestError):
            if raise_on_error:
                raise cached
            return None
        return cached

    def get_version(self, version_id: int | str) -> dict | None:
        return self._get_json(f"{MODEL_VERSION_BY_ID_URL}/{version_id}")

    def get_model_versions_for_model(self, model_id: int | str) -> tuple[str, list[dict], bool]:
        model = self.get_model(model_id, raise_on_error=True)
        if not model:
            return ("", [], False)
        versions = model.get("modelVersions") or []
        creator = model.get("creator")
        creator_name = ""
        if isinstance(creator, dict):
            creator_name = creator.get("username") or ""
        is_nsfw = bool(model.get("nsfw"))
        return (creator_name, versions, is_nsfw)

    def model_page_url(self, model_id: int | str) -> str:
        return f"{MODEL_PAGE_BASE_URL}/{model_id}"

    def version_page_url(self, model_id: int | str, version_id: int | str | None = None) -> str:
        if version_id:
            return f"{MODEL_PAGE_BASE_URL}/{model_id}?modelVersionId={version_id}"
        return self.model_page_url(model_id)

    def download_file(
        self,
        url: str,
        target_path: Path,
        max_bytes: int = 10_000_000,
        allow_truncated: bool = False,
    ) -> bool:
        """Download a file (e.g. preview image) to *target_path*. Returns True on success.

        With ``allow_truncated`` the first ``max_bytes`` are kept when the
        source is larger, instead of treating the size limit as a failure.
        """
        tmp_path = target_path.with_suffix(f"{target_path.suffix}.tmp")
        try:
            with self.session.get(
                url, timeout=self.timeout_seconds, headers=self.default_headers, stream=True
            ) as response:
                if not response.ok:
                    return False
                target_path.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                truncated = False
                with tmp_path.open("wb") as fh:
                    for chunk in response.iter_content(chunk_size=8192):
                        if written + len(chunk) > max_bytes:
                            if allow_truncated:
                                fh.write(chunk[: max_bytes - written])
                            truncated = True
                            break
                        fh.write(chunk)
                        written += len(chunk)
            # Windows cannot unlink a file that is still open, so delete only
            # after both the file handle and the response are closed.
            if truncated and not allow_truncated:
                tmp_path.unlink(missing_ok=True)
                return False
            tmp_path.replace(target_path)
            return True
        except Exception:  # noqa: BLE001
            tmp_path.unlink(missing_ok=True)
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
        max_bytes: int = 80_000_000,
        head_bytes: int = 12_000_000,
    ) -> bool:
        """Download a video URL and extract its first frame to PNG via ffmpeg.

        Preview videos on Civitai are regularly 30-60MB, so the first
        ``head_bytes`` are tried first — enough to decode frame one of a
        web-optimized MP4 — before falling back to the full download.
        """
        ffmpeg_path = _resolve_ffmpeg()
        if not ffmpeg_path:
            return False

        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_video = target_path.with_suffix(".preview_video.tmp.mp4")
        tmp_png = target_path.with_suffix(".preview_frame.tmp.png")

        try:
            if not self.download_file(url, tmp_video, max_bytes=head_bytes, allow_truncated=True):
                return False
            if _extract_first_frame(ffmpeg_path, tmp_video, tmp_png, target_path):
                return True

            # A file smaller than head_bytes was complete — retrying with a
            # full download cannot help.
            was_truncated = tmp_video.exists() and tmp_video.stat().st_size >= head_bytes
            if not was_truncated:
                return False

            # Slow path for videos whose metadata sits at the end of the file.
            if not self.download_file(url, tmp_video, max_bytes=max_bytes):
                return False
            return _extract_first_frame(ffmpeg_path, tmp_video, tmp_png, target_path)
        finally:
            tmp_video.unlink(missing_ok=True)

    def _get_json(self, url: str, *, raise_on_error: bool = False) -> dict | None:
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
                    if "Authorization" in self.default_headers:
                        detail = "Civitai rejected the API key. Verify it in the settings panel."
                    else:
                        detail = "Civitai denied the request. This resource may require an API key — set one in the settings panel."
                    print(f"Civitai updater: {response.status_code} {response.reason} for {url}. {detail}")
                    if raise_on_error:
                        raise CivitaiRequestError(f"{response.status_code} {response.reason}. {detail}")
                    return None
                if response.status_code in (400, 404):
                    if raise_on_error:
                        raise CivitaiRequestError(
                            f"{response.status_code} {response.reason}. The model may have been removed from Civitai."
                        )
                    return None
                last_error = f"{response.status_code} {response.reason}"

            if attempt < self.max_retries:
                time.sleep(_retry_delay_seconds(attempt))

        if last_error:
            print(f"Civitai updater request failed: {url} :: {last_error}")
            if raise_on_error:
                raise CivitaiRequestError(f"{url} :: {last_error}")
        return None

    def _download_bytes(self, url: str, max_bytes: int) -> bytes | None:
        try:
            with self.session.get(
                url,
                timeout=self.timeout_seconds,
                headers=self.default_headers,
                stream=True,
            ) as response:
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


def _extract_first_frame(ffmpeg_path: str, video_path: Path, tmp_png: Path, target_path: Path) -> bool:
    try:
        process = subprocess.run(  # noqa: S603
            [
                ffmpeg_path,
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(video_path),
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


_ffmpeg_cache: dict = {}


def _resolve_ffmpeg() -> str | None:
    """Locate ffmpeg once per process; warn once when it is unavailable."""
    if "path" in _ffmpeg_cache:
        return _ffmpeg_cache["path"]

    path = shutil.which("ffmpeg")
    if not path:
        try:
            # imageio-ffmpeg ships a bundled binary and is a common transitive
            # dependency in ComfyUI installs even when ffmpeg is not on PATH.
            import imageio_ffmpeg

            path = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:  # noqa: BLE001 - any failure means "no ffmpeg available"
            path = None

    if not path:
        print(
            "Civitai updater: ffmpeg was not found, so video previews cannot be "
            "converted to PNG. Install ffmpeg (or the imageio-ffmpeg Python "
            "package) to enable video preview thumbnails."
        )
    _ffmpeg_cache["path"] = path
    return path


def _retry_delay_seconds(attempt: int) -> float:
    return min(10.0, 0.5 * (2**attempt))


def _is_png_data(data: bytes) -> bool:
    return data.startswith(b"\x89PNG\r\n\x1a\n")


class CivitaiRequestError(RuntimeError):
    """Raised when a Civitai request fails after retries."""

