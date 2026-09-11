from __future__ import annotations

import json
from pathlib import Path
import threading

from .constants import ARCHIVED_UPDATES_FILENAME
from .sidecar import quarantine_corrupt_file


class ArchivedUpdateStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / ARCHIVED_UPDATES_FILENAME
        self._lock = threading.Lock()
        self._data: dict[str, set[str]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            self._save()
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError as exc:
            # Leave the file untouched: saving now would replace every hidden
            # version with an empty list.
            print(f"Civitai updater: could not read {self.path} ({exc}); hidden versions are unavailable this session.")
            return
        except json.JSONDecodeError as exc:
            backup = quarantine_corrupt_file(self.path)
            print(
                f"Civitai updater: {self.path} is not valid JSON ({exc}). "
                f"It was moved to {backup} and an empty list was written."
            )
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        entries = payload.get("archivedUpdates", {})
        if not isinstance(entries, dict):
            entries = {}
        self._data = {
            str(model_id): {str(version_id) for version_id in version_ids if str(version_id)}
            for model_id, version_ids in entries.items()
            if isinstance(version_ids, list)
        }
        self._save()

    def _save(self) -> None:
        payload = {
            "archivedUpdates": {
                model_id: sorted(version_ids)
                for model_id, version_ids in sorted(self._data.items())
                if version_ids
            }
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp_path.replace(self.path)

    def archive(self, model_id: str | int, version_ids: list[str | int]) -> list[str]:
        model_key = str(model_id or "").strip()
        cleaned = _normalize_version_ids(version_ids)
        if not model_key or not cleaned:
            return []
        with self._lock:
            current = self._data.setdefault(model_key, set())
            current.update(cleaned)
            self._save()
            return sorted(current)

    def restore(self, model_id: str | int, version_ids: list[str | int]) -> list[str]:
        model_key = str(model_id or "").strip()
        cleaned = set(_normalize_version_ids(version_ids))
        if not model_key:
            return []
        with self._lock:
            current = self._data.get(model_key, set())
            current.difference_update(cleaned)
            if current:
                self._data[model_key] = current
            else:
                self._data.pop(model_key, None)
            self._save()
            return sorted(self._data.get(model_key, set()))

    def snapshot(self) -> dict[str, set[str]]:
        with self._lock:
            return {model_id: set(version_ids) for model_id, version_ids in self._data.items()}

    def get_archived_versions(self, model_id: str | int) -> set[str]:
        model_key = str(model_id or "").strip()
        with self._lock:
            return set(self._data.get(model_key, set()))


def _normalize_version_ids(version_ids: list[str | int] | None) -> list[str]:
    if not isinstance(version_ids, list):
        return []
    normalized = set()
    for version_id in version_ids:
        if version_id is None:
            continue
        cleaned = str(version_id).strip()
        if cleaned:
            normalized.add(cleaned)
    return sorted(normalized)
