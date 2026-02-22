from __future__ import annotations

import json
from pathlib import Path

from .constants import INFO_SIDECAR_SUFFIX, PREVIEW_SIDECAR_SUFFIX


def info_sidecar_path(model_path: Path) -> Path:
    return model_path.with_suffix(f"{INFO_SIDECAR_SUFFIX}")


def preview_sidecar_path(model_path: Path) -> Path:
    return model_path.with_suffix(f"{PREVIEW_SIDECAR_SUFFIX}")


def read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(path)

