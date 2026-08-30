from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from comfy_updater.civitai_client import CivitaiRequestError
from comfy_updater.config_store import ConfigStore
from comfy_updater.sidecar import info_sidecar_path, read_json, write_json
from comfy_updater.updater_service import UpdaterService


class FailingModelClient:
    def get_model_versions_for_model(self, model_id):
        raise CivitaiRequestError(f"https://civitai.com/api/v1/models/{model_id} :: 500 Internal Server Error")

    def model_page_url(self, model_id, nsfw=False):  # noqa: ARG002
        return f"https://civitai.red/models/{model_id}"

    def version_page_url(self, model_id, version_id=None, nsfw=False):  # noqa: ARG002
        if version_id:
            return f"https://civitai.red/models/{model_id}?modelVersionId={version_id}"
        return self.model_page_url(model_id)


class MetadataOnlyClient:
    def __init__(self):
        self.requested_version_ids = []

    def get_version(self, version_id):
        self.requested_version_ids.append(version_id)
        return {
            "id": version_id,
            "modelId": 123,
            "name": "Local Version Refreshed",
            "baseModel": "SDXL 1.0",
            "publishedAt": "2026-03-05T00:00:00Z",
            "model": {"name": "Example Model"},
            "images": [],
        }

    def get_model_versions_for_model(self, model_id):  # noqa: ARG002
        return (
            "artist",
            [
                {
                    "id": 789,
                    "name": "New Version",
                    "baseModel": "SDXL 1.0",
                    "publishedAt": "2026-03-06T00:00:00Z",
                    "images": [],
                },
                {
                    "id": 456,
                    "name": "Local Version",
                    "baseModel": "SDXL 1.0",
                    "publishedAt": "2026-03-05T00:00:00Z",
                    "images": [],
                },
                {
                    "id": 111,
                    "name": "Old Version",
                    "baseModel": "SDXL 1.0",
                    "publishedAt": "2026-03-01T00:00:00Z",
                    "images": [],
                },
            ],
            False,
        )

    def model_page_url(self, model_id, nsfw=False):  # noqa: ARG002
        return f"https://civitai.red/models/{model_id}"

    def version_page_url(self, model_id, version_id=None, nsfw=False):  # noqa: ARG002
        return f"https://civitai.red/models/{model_id}?modelVersionId={version_id}"


class PreviewBackfillClient(MetadataOnlyClient):
    def __init__(self):
        super().__init__()
        self.downloaded = []

    def get_model_versions_for_model(self, model_id):  # noqa: ARG002
        return (
            "artist",
            [
                {
                    "id": 456,
                    "name": "Local Version",
                    "baseModel": "SDXL 1.0",
                    "publishedAt": "2026-03-05T00:00:00Z",
                    "images": [{"type": "image", "url": "https://img.example/local.jpeg"}],
                },
            ],
            False,
        )

    def download_image_as_png(self, url, target_path, max_bytes=10_000_000):  # noqa: ARG002
        self.downloaded.append((url, target_path))
        return True


class UpdaterServiceErrorTests(unittest.TestCase):
    def test_model_lookup_failure_returns_error_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "example.safetensors"
            model_path.write_bytes(b"not a real model")
            write_json(
                info_sidecar_path(model_path),
                {
                    "id": 456,
                    "modelId": 123,
                    "name": "Local Version",
                    "baseModel": "SDXL 1.0",
                    "model": {"name": "Example Model"},
                    "images": [],
                },
            )

            item = UpdaterService(None)._process_one(
                client=FailingModelClient(),
                model_path=model_path,
                model_type="lora",
                mode="check",
                refetch_metadata=False,
                force_rehash=False,
            )

            self.assertEqual("error", item["status"])
            self.assertEqual("123", item["modelId"])
            self.assertIn("500 Internal Server Error", item["error"])
            self.assertFalse(item["hasUpdate"])

    def test_metadata_only_check_uses_sidecar_even_when_force_rehash_is_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            info_path = Path(tmpdir) / "example.civitai.info"
            preview_path = Path(tmpdir) / "example.preview.png"
            write_json(
                info_path,
                {
                    "id": 456,
                    "modelId": 123,
                    "name": "Local Version",
                    "baseModel": "SDXL 1.0",
                    "publishedAt": "2026-03-05T00:00:00Z",
                    "model": {"name": "Example Model"},
                    "images": [],
                },
            )

            with patch("comfy_updater.updater_service.sha256_file") as hash_file:
                item = UpdaterService(None)._process_one(
                    client=MetadataOnlyClient(),
                    model_path=info_path,
                    model_type="lora",
                    mode="check",
                    refetch_metadata=False,
                    force_rehash=True,
                    info_path=info_path,
                    preview_path=preview_path,
                    metadata_only=True,
                )

            hash_file.assert_not_called()
            self.assertEqual("ok", item["status"])
            self.assertTrue(item["metadataOnly"])
            self.assertEqual("456", item["localVersionId"])
            self.assertEqual(["789"], [version["versionId"] for version in item["remoteVersions"] if version["versionDate"] > item["localVersionDate"]])
            self.assertEqual("789", item["latestVersionId"])

    def test_metadata_only_refresh_uses_version_id_and_preserves_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            info_path = Path(tmpdir) / "example.civitai.info"
            preview_path = Path(tmpdir) / "example.preview.png"
            write_json(info_path, {"id": 456, "modelId": 123})
            client = MetadataOnlyClient()

            with patch("comfy_updater.updater_service.sha256_file") as hash_file:
                item = UpdaterService(None)._process_one(
                    client=client,
                    model_path=info_path,
                    model_type="lora",
                    mode="scan",
                    refetch_metadata=True,
                    force_rehash=True,
                    info_path=info_path,
                    preview_path=preview_path,
                    metadata_only=True,
                )

            hash_file.assert_not_called()
            self.assertEqual([456], client.requested_version_ids)
            self.assertEqual(str(info_path), item["modelPath"])
            self.assertTrue(item["metadataOnly"])
            self.assertEqual("Local Version Refreshed", read_json(info_path)["name"])

    def test_check_backfills_local_preview_from_remote_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "example.safetensors"
            model_path.write_bytes(b"weights")
            preview_path = Path(tmpdir) / "example.preview.png"
            # A sidecar written while the API was SFW-filtered: no images.
            write_json(
                info_sidecar_path(model_path),
                {
                    "id": 456,
                    "modelId": 123,
                    "name": "Local Version",
                    "baseModel": "SDXL 1.0",
                    "publishedAt": "2026-03-05T00:00:00Z",
                    "model": {"name": "Example Model"},
                    "images": [],
                },
            )
            client = PreviewBackfillClient()

            item = UpdaterService(None)._process_one(
                client=client,
                model_path=model_path,
                model_type="lora",
                mode="check",
                refetch_metadata=False,
                force_rehash=False,
            )

            self.assertEqual("ok", item["status"])
            self.assertEqual("https://img.example/local.jpeg", item["localPreviewUrl"])
            self.assertEqual("image", item["localPreviewType"])
            self.assertEqual(
                [("https://img.example/local.jpeg", preview_path)],
                client.downloaded,
            )

    def test_current_file_paths_follow_sidecar_setting_and_validity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "models"
            root.mkdir()
            info_path = root / "example.civitai.info"
            write_json(info_path, {"id": 456, "modelId": 123})

            store = ConfigStore(Path(tmpdir) / "data")
            store.update(
                {
                    "useComfyPaths": False,
                    "useExtraModelPaths": False,
                    "useCustomPaths": True,
                    "customPaths": {"lora": [str(root)]},
                    "treatSidecarsAsInstalled": True,
                }
            )
            service = UpdaterService(store)

            self.assertEqual({str(info_path).lower()}, service.list_current_file_paths())

            write_json(info_path, {"modelId": 123})
            self.assertEqual(set(), service.list_current_file_paths())

            write_json(info_path, {"id": 456, "modelId": 123})
            store.update({"treatSidecarsAsInstalled": False})
            self.assertEqual(set(), service.list_current_file_paths())

    def test_current_file_inspection_returns_non_fatal_sidecar_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "models"
            root.mkdir()
            info_path = root / "broken.civitai.info"
            info_path.write_bytes(b"{\x8f}")

            store = ConfigStore(Path(tmpdir) / "data")
            store.update(
                {
                    "useComfyPaths": False,
                    "useExtraModelPaths": False,
                    "useCustomPaths": True,
                    "customPaths": {"lora": [str(root)]},
                    "treatSidecarsAsInstalled": True,
                }
            )

            paths, warnings = UpdaterService(store).inspect_current_files()

            self.assertEqual(set(), paths)
            self.assertEqual(1, len(warnings))
            self.assertEqual(str(info_path), warnings[0]["path"])
            self.assertEqual("invalid_encoding", warnings[0]["code"])


if __name__ == "__main__":
    unittest.main()
