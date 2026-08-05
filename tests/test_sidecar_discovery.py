from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from comfy_updater.config_store import ConfigStore
from comfy_updater.path_resolver import list_model_files
from comfy_updater.sidecar import (
    SIDECAR_ERROR_INVALID_ENCODING,
    SIDECAR_ERROR_INVALID_JSON,
    SIDECAR_ERROR_SAFETENSORS,
    SIDECAR_ERROR_TOO_LARGE,
    read_json_diagnostic,
    write_json,
)


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
            (root / "binary.civitai.info").write_bytes(b"{\x8f}")
            write_json(root / "missing-version.civitai.info", {"modelId": 123})
            write_json(root / "missing-model.civitai.info", {"id": 456})
            (root / "preview.preview.png").write_bytes(b"preview")
            warnings = []

            files = list_model_files(
                {"checkpoint": [root]}, include_sidecar_only=True, sidecar_warnings=warnings
            )

            self.assertEqual([], files)
            self.assertEqual(
                {SIDECAR_ERROR_INVALID_ENCODING, SIDECAR_ERROR_INVALID_JSON},
                {warning["code"] for warning in warnings},
            )

    def test_legacy_unicode_sidecars_are_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            payload = '{"id": 456, "modelId": 123}'
            for index, encoding in enumerate(("utf-8-sig", "utf-16", "utf-32")):
                (root / f"tracked-{index}.civitai.info").write_text(payload, encoding=encoding)

            files = list_model_files({"lora": [root]}, include_sidecar_only=True)

            self.assertEqual(3, len(files))

    def test_oversized_sidecar_is_classified(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            info_path = Path(tmpdir) / "oversized.civitai.info"
            write_json(info_path, {"id": 456, "modelId": 123})

            with patch("comfy_updater.sidecar._MAX_JSON_BYTES", info_path.stat().st_size - 1):
                payload, error = read_json_diagnostic(info_path)

            self.assertIsNone(payload)
            self.assertEqual(SIDECAR_ERROR_TOO_LARGE, error)

    def test_misnamed_safetensors_sidecar_has_actionable_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            info_path = root / "model.civitai.info"
            header = b'{"tensor":{"dtype":"F32","shape":[1],"data_offsets":[0,4]}}'
            info_path.write_bytes(len(header).to_bytes(8, "little") + header + b"\x00\x00\x00\x00")
            warnings = []

            files = list_model_files(
                {"checkpoint": [root]}, include_sidecar_only=True, sidecar_warnings=warnings
            )

            self.assertEqual([], files)
            self.assertEqual(1, len(warnings))
            self.assertEqual(SIDECAR_ERROR_SAFETENSORS, warnings[0]["code"])
            self.assertEqual(".safetensors", warnings[0]["suggestedExtension"])
            self.assertIn("Rename", warnings[0]["message"])

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
