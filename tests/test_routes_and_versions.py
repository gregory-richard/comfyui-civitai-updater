from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from comfy_updater.config_store import ConfigStore
from comfy_updater.constants import CACHE_SCHEMA_VERSION
from comfy_updater.routes import (
    _merge_check_items,
    _normalize_archive_payload,
    _normalize_config_payload,
    _seed_items_from_cache,
)
from comfy_updater.updater_service import _version_date


class RouteAndVersionHelperTests(unittest.TestCase):
    def test_normalize_archive_payload(self) -> None:
        model_id, version_ids = _normalize_archive_payload({
            "modelId": 42,
            "versionIds": ["a", "b", "a", "", None],
        })
        self.assertEqual("42", model_id)
        self.assertEqual(["a", "b"], version_ids)

    def test_normalize_config_payload_keeps_custom_paths_partial(self) -> None:
        incoming = _normalize_config_payload({
            "customPaths": {"checkpoint": "C:/a;C:/b", "lora": []},
        })

        self.assertEqual(
            {"checkpoint": ["C:/a", "C:/b"], "lora": []},
            incoming["customPaths"],
        )
        # Model types the client did not send must stay absent so their
        # stored custom paths survive a partial settings sync.
        self.assertNotIn("embedding", incoming["customPaths"])

    def test_partial_settings_sync_preserves_other_custom_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ConfigStore(Path(tmpdir))
            store.update({"customPaths": {"embedding": ["C:/embeddings"]}})

            # Simulates the frontend sync payload, which omits "embedding".
            incoming = _normalize_config_payload({
                "customPaths": {"checkpoint": ["C:/checkpoints"], "lora": [], "vae": [], "unet": []},
            })
            updated = store.update(incoming)

            self.assertEqual(["C:\\embeddings"], updated["customPaths"]["embedding"])
            self.assertEqual(["C:\\checkpoints"], updated["customPaths"]["checkpoint"])

    def test_seed_items_from_cache_keeps_every_type_and_marks_items(self) -> None:
        cache = {
            "schemaVersion": CACHE_SCHEMA_VERSION,
            "items": [
                {
                    "modelPath": "C:\\models\\a.safetensors",
                    "modelType": "lora",
                    "modelUrl": "https://civitai.com/models/1",
                    "remoteVersions": [],
                },
                {"modelPath": "C:\\models\\b.safetensors", "modelType": "checkpoint", "remoteVersions": []},
            ],
        }

        seeded = _seed_items_from_cache(cache)

        # A check limited to one type must still show the others while it runs.
        self.assertEqual(2, len(seeded))
        self.assertTrue(all(item["_seeded"] for item in seeded))
        self.assertEqual("C:\\models\\a.safetensors", seeded[0]["modelPath"])
        self.assertEqual("https://civitai.red/models/1", seeded[0]["modelUrl"])

    def test_seed_items_from_cache_rejects_missing_or_outdated_cache(self) -> None:
        self.assertEqual([], _seed_items_from_cache(None))
        self.assertEqual(
            [],
            _seed_items_from_cache(
                {"schemaVersion": CACHE_SCHEMA_VERSION - 1, "items": [{"modelType": "lora"}]},
            ),
        )

    def test_merge_check_items_replaces_checked_types_and_keeps_the_rest(self) -> None:
        cache = {
            "schemaVersion": CACHE_SCHEMA_VERSION,
            "items": [
                {"modelPath": "C:\\models\\old-lora.safetensors", "modelType": "lora", "remoteVersions": []},
                {
                    "modelPath": "C:\\models\\ckpt.safetensors",
                    "modelType": "checkpoint",
                    "modelUrl": "https://civitai.com/models/7",
                    "remoteVersions": [],
                },
            ],
        }
        fresh = [{"modelPath": "C:\\models\\new-lora.safetensors", "modelType": "lora", "remoteVersions": []}]

        merged = _merge_check_items(cache, fresh, ["lora"])

        paths = [item["modelPath"] for item in merged]
        # The deleted lora is gone, the new one is in, the checkpoint survives.
        self.assertNotIn("C:\\models\\old-lora.safetensors", paths)
        self.assertIn("C:\\models\\new-lora.safetensors", paths)
        self.assertIn("C:\\models\\ckpt.safetensors", paths)
        checkpoint = next(item for item in merged if item["modelType"] == "checkpoint")
        self.assertEqual("https://civitai.red/models/7", checkpoint["modelUrl"])

    def test_merge_check_items_without_types_or_cache_returns_fresh(self) -> None:
        fresh = [{"modelPath": "a", "modelType": "lora"}]
        self.assertEqual(fresh, _merge_check_items(None, fresh, ["lora"]))
        self.assertEqual(fresh, _merge_check_items({"schemaVersion": 1, "items": [{"modelType": "vae"}]}, fresh, ["lora"]))
        self.assertEqual(fresh, _merge_check_items({"schemaVersion": CACHE_SCHEMA_VERSION, "items": [{"modelType": "vae"}]}, fresh, None))

    def test_version_date_prefers_published_and_falls_back_to_created(self) -> None:
        self.assertEqual(
            "2026-03-10T00:00:00Z",
            _version_date({"publishedAt": "2026-03-10T00:00:00Z", "createdAt": "2026-03-01T00:00:00Z"}),
        )
        self.assertEqual(
            "2026-03-01T00:00:00Z",
            _version_date({"publishedAt": "", "createdAt": "2026-03-01T00:00:00Z"}),
        )


if __name__ == "__main__":
    unittest.main()
