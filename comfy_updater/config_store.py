from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from .constants import SUPPORTED_MODEL_TYPES


DEFAULT_CONFIG = {
    "apiKey": "",
    "requestTimeoutSeconds": 30,
    "maxRetries": 4,
    "requestDelayMs": 120,
    "useComfyPaths": True,
    "useExtraModelPaths": True,
    "useCustomPaths": True,
    "customPaths": {model_type: [] for model_type in SUPPORTED_MODEL_TYPES},
}


class ConfigStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.config_path = self.data_dir / "config.json"
        self._config = deepcopy(DEFAULT_CONFIG)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        if not self.config_path.is_file():
            self._save()
            return

        try:
            loaded = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}

        self._config = self._merged(loaded)
        self._save()

    def _merged(self, incoming: dict) -> dict:
        merged = deepcopy(DEFAULT_CONFIG)

        if not isinstance(incoming, dict):
            return merged

        for key in (
            "apiKey",
            "requestTimeoutSeconds",
            "maxRetries",
            "requestDelayMs",
            "useComfyPaths",
            "useExtraModelPaths",
            "useCustomPaths",
        ):
            if key in incoming:
                merged[key] = incoming[key]

        custom_paths = incoming.get("customPaths", {})
        if isinstance(custom_paths, dict):
            for model_type in SUPPORTED_MODEL_TYPES:
                val = custom_paths.get(model_type, [])
                if isinstance(val, list):
                    merged["customPaths"][model_type] = [
                        str(Path(path))
                        for path in val
                        if isinstance(path, str) and path.strip()
                    ]

        merged["requestTimeoutSeconds"] = _int_in_range(
            merged["requestTimeoutSeconds"], default=30, minimum=5, maximum=300
        )
        merged["maxRetries"] = _int_in_range(
            merged["maxRetries"], default=4, minimum=0, maximum=10
        )
        merged["requestDelayMs"] = _int_in_range(
            merged["requestDelayMs"], default=120, minimum=0, maximum=3000
        )

        if not isinstance(merged["apiKey"], str):
            merged["apiKey"] = ""
        merged["useComfyPaths"] = bool(merged["useComfyPaths"])
        merged["useExtraModelPaths"] = bool(merged["useExtraModelPaths"])
        merged["useCustomPaths"] = bool(merged["useCustomPaths"])

        return merged

    def _save(self) -> None:
        self.config_path.write_text(
            json.dumps(self._config, indent=2),
            encoding="utf-8",
        )

    def get(self) -> dict:
        return deepcopy(self._config)

    def get_public(self) -> dict:
        cfg = self.get()
        cfg["hasApiKey"] = bool(cfg.get("apiKey", "").strip())
        cfg["apiKey"] = ""
        return cfg

    def update(self, incoming: dict) -> dict:
        incoming = incoming or {}
        merged = self._merged({**self._config, **incoming})
        if "customPaths" in incoming and isinstance(incoming["customPaths"], dict):
            current_custom = deepcopy(self._config.get("customPaths", {}))
            normalized_custom = self._merged({"customPaths": incoming["customPaths"]})["customPaths"]
            for model_type in SUPPORTED_MODEL_TYPES:
                if model_type in incoming["customPaths"]:
                    current_custom[model_type] = normalized_custom[model_type]
            merged["customPaths"] = current_custom
        self._config = merged
        self._save()
        return self.get()


def _int_in_range(value, default: int, minimum: int, maximum: int) -> int:
    try:
        as_int = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, as_int))
