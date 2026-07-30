from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from comfy_updater.config_store import ConfigStore
from comfy_updater.path_resolver import list_model_files
from comfy_updater.sidecar import write_json


class SidecarDiscoveryTests(unittest.TestCase):
    def test_sidecar_setting_defaults_true_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            store = ConfigStore(data_dir)
            self.assertTrue(store.get()["treatSidecarsAsInstalled"])

            store.update({"treatSidecarsAsInstalled": False})

            self.assertFalse(ConfigStore(data_dir).get()["treatSidecarsAsInstalled"])

    def test_valid_orphan_sidecar_is_discovered_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            info_path = root / "tracked.civitai.info"
            preview_path = root / "tracked.preview.png"
            write_json(info_path, {"id": 456, "modelId": 123})
            preview_path.write_bytes(b"preview")

            files = list_model_files({"lora": [root]}, include_sidecar_only=True)

            self.assertEqual(1, len(files))
            self.assertEqual(info_path, files[0]["path"])
            self.assertEqual(info_path, files[0]["infoPath"])
            self.assertEqual(preview_path, files[0]["previewPath"])
            self.assertTrue(files[0]["metadataOnly"])

    def test_sidecar_only_discovery_can_be_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_json(root / "tracked.civitai.info", {"id": 456, "modelId": 123})

            files = list_model_files({"lora": [root]}, include_sidecar_only=False)

            self.assertEqual([], files)

    def test_invalid_sidecars_and_preview_only_files_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "broken.civitai.info").write_text("{", encoding="utf-8")
            write_json(root / "missing-version.civitai.info", {"modelId": 123})
            write_json(root / "missing-model.civitai.info", {"id": 456})
            (root / "preview.preview.png").write_bytes(b"preview")

            files = list_model_files({"checkpoint": [root]}, include_sidecar_only=True)

            self.assertEqual([], files)

    def test_physical_weight_suppresses_matching_sidecar_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            model_path = root / "nested.name.safetensors"
            info_path = root / "nested.name.civitai.info"
            model_path.write_bytes(b"model")
            write_json(info_path, {"id": 456, "modelId": 123})

            files = list_model_files({"checkpoint": [root]}, include_sidecar_only=True)

            self.assertEqual(1, len(files))
            self.assertEqual(model_path, files[0]["path"])
            self.assertEqual(info_path, files[0]["infoPath"])
            self.assertFalse(files[0]["metadataOnly"])


if __name__ == "__main__":
    unittest.main()
