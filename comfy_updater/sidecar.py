from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .constants import INFO_SIDECAR_SUFFIX, PREVIEW_SIDECAR_SUFFIX, SUPPORTED_MODEL_EXTENSIONS

_MAX_JSON_BYTES = 16 * 1024 * 1024

SIDECAR_ERROR_SAFETENSORS = "safetensors_misnamed"
SIDECAR_ERROR_TOO_LARGE = "too_large"
SIDECAR_ERROR_INVALID_ENCODING = "invalid_encoding"
SIDECAR_ERROR_INVALID_JSON = "invalid_json"
SIDECAR_ERROR_READ = "read_error"


def info_sidecar_path(model_path: Path) -> Path:
    return model_path.with_suffix(f"{INFO_SIDECAR_SUFFIX}")


def preview_sidecar_path(model_path: Path) -> Path:
    return model_path.with_suffix(f"{PREVIEW_SIDECAR_SUFFIX}")


def model_file_path(info_path: Path, info: dict | None = None) -> Path:
    """Where the weights described by a metadata-only sidecar would live.

    The sidecar names the file Civitai serves, so its extension is reused;
    anything unusable falls back to .safetensors.
    """
    base_name = info_path.name[: -len(INFO_SIDECAR_SUFFIX)]
    return info_path.with_name(f"{base_name}{_primary_file_extension(info)}")


def _primary_file_extension(info: dict | None) -> str:
    files = info.get("files") if isinstance(info, dict) else None
    entries = [entry for entry in files if isinstance(entry, dict)] if isinstance(files, list) else []
    primary = next((entry for entry in entries if entry.get("primary")), None) or next(
        (entry for entry in entries if entry.get("type") == "Model"), None
    )
    suffix = Path(str(primary.get("name") or "")).suffix.lower() if primary else ""
    return suffix if suffix in SUPPORTED_MODEL_EXTENSIONS else ".safetensors"


def read_json(path: Path) -> dict | None:
    payload, _error = read_json_diagnostic(path)
    return payload


def read_data_file(path: Path) -> dict | None:
    """Read one of the plugin's own JSON files.

    Unlike a sidecar it has no size cap: the saved check results grow with the
    library and pass 16 MB at a few thousand models.
    """
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def read_json_diagnostic(path: Path) -> tuple[dict | None, str | None]:
    if not path.is_file():
        return None, None
    try:
        file_size = path.stat().st_size
        if file_size > _MAX_JSON_BYTES:
            with path.open("rb") as file_handle:
                prefix = file_handle.read(9)
            error = SIDECAR_ERROR_SAFETENSORS if _looks_like_safetensors(prefix, file_size) else SIDECAR_ERROR_TOO_LARGE
            return None, error

        # Let the JSON decoder detect UTF-8/16/32 (and their BOM variants)
        # while keeping malformed or binary sidecars from breaking a scan.
        with path.open("rb") as file_handle:
            raw = file_handle.read(_MAX_JSON_BYTES + 1)
        if len(raw) > _MAX_JSON_BYTES:
            return None, SIDECAR_ERROR_TOO_LARGE
        if _looks_like_safetensors(raw[:9], file_size):
            return None, SIDECAR_ERROR_SAFETENSORS
        try:
            payload = json.loads(raw)
        except UnicodeDecodeError:
            return None, SIDECAR_ERROR_INVALID_ENCODING
        except json.JSONDecodeError:
            return None, SIDECAR_ERROR_INVALID_JSON
        if not isinstance(payload, dict):
            # Valid JSON but not an object (e.g. a list or bare string) —
            # callers rely on dict semantics, so classify it as invalid.
            return None, SIDECAR_ERROR_INVALID_JSON
        return payload, None
    except OSError:
        return None, SIDECAR_ERROR_READ


def _looks_like_safetensors(prefix: bytes, file_size: int) -> bool:
    if len(prefix) < 9 or prefix[8:9] != b"{":
        return False
    header_size = int.from_bytes(prefix[:8], byteorder="little", signed=False)
    return 2 <= header_size <= file_size - 8


def quarantine_corrupt_file(path: Path) -> Path:
    """Move a file that failed to parse aside so its contents can be recovered by hand."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.corrupt-{stamp}")
    counter = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.corrupt-{stamp}-{counter}")
        counter += 1
    path.replace(backup)
    return backup


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    try:
        tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp_path.replace(path)
    except OSError:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
