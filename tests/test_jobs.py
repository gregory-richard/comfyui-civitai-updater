from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from comfy_updater.archived_updates import ArchivedUpdateStore
from comfy_updater.jobs import JobManager, JobRecord


def make_item(
    *,
    model_id: str,
    model_name: str,
    model_type: str,
    local_version_id: str,
    local_version_name: str,
    local_version_date: str,
    base_model: str,
    model_path: str,
    remote_versions: list[dict],
    nsfw: bool = False,
) -> dict:
    primary = remote_versions[0] if remote_versions else {}
    return {
        "modelId": model_id,
        "modelName": model_name,
        "modelType": model_type,
        "creatorName": "artist",
        "modelUrl": f"https://civitai.com/models/{model_id}",
        "modelPath": model_path,
        "baseModel": base_model,
        "localVersionId": local_version_id,
        "localVersionName": local_version_name,
        "localVersionDate": local_version_date,
        "localPreviewUrl": "",
        "localPreviewType": "image",
        "remoteVersions": remote_versions,
        "latestVersionId": primary.get("versionId", ""),
        "latestVersionName": primary.get("versionName", ""),
        "latestBaseModel": primary.get("baseModel", ""),
        "latestVersionDate": primary.get("versionDate", ""),
        "previewUrl": primary.get("previewUrl", ""),
        "previewType": primary.get("previewType", "image"),
        "versionUrl": primary.get("versionUrl", ""),
        "downloadUrl": primary.get("downloadUrl", ""),
        "hasUpdate": bool(remote_versions),
        "status": "ok",
        "nsfw": nsfw,
    }


class JobManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.archive_store = ArchivedUpdateStore(Path(self.tmpdir.name))
        self.manager = JobManager(self.archive_store)
        self.job = JobRecord(id="job-1", type="check-updates", status="completed")
        self.manager._jobs[self.job.id] = self.job

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_grouping_uses_newest_local_date_and_archive_partition(self) -> None:
        remote_versions = [
            {
                "versionId": "v-new-2",
                "versionName": "Newest",
                "versionDate": "2026-03-07T00:00:00Z",
                "baseModel": "SDXL 1.0",
                "previewUrl": "",
                "previewType": "image",
                "versionUrl": "https://example.com/v-new-2",
                "downloadUrl": "https://example.com/d-new-2",
            },
            {
                "versionId": "v-new-1",
                "versionName": "Newer",
                "versionDate": "2026-03-06T00:00:00Z",
                "baseModel": "SDXL 1.0",
                "previewUrl": "",
                "previewType": "image",
                "versionUrl": "https://example.com/v-new-1",
                "downloadUrl": "https://example.com/d-new-1",
            },
            {
                "versionId": "v-old",
                "versionName": "Older",
                "versionDate": "2026-03-04T00:00:00Z",
                "baseModel": "SDXL 1.0",
                "previewUrl": "",
                "previewType": "image",
                "versionUrl": "https://example.com/v-old",
                "downloadUrl": "https://example.com/d-old",
            },
        ]
        self.job.items = [
            make_item(
                model_id="m1",
                model_name="Model One",
                model_type="checkpoint",
                local_version_id="v-local-a",
                local_version_name="Photo 1",
                local_version_date="2026-03-01T00:00:00Z",
                base_model="SDXL 1.0",
                model_path="C:\\models\\one-a.safetensors",
                remote_versions=remote_versions,
            ),
            make_item(
                model_id="m1",
                model_name="Model One",
                model_type="checkpoint",
                local_version_id="v-local-b",
                local_version_name="Photo 2",
                local_version_date="2026-03-05T00:00:00Z",
                base_model="SDXL 1.0",
                model_path="C:\\models\\one-b.safetensors",
                remote_versions=remote_versions,
            ),
        ]
        self.archive_store.archive("m1", ["v-new-1"])

        total, _, _, items, _ = self.manager.get_items("job-1", mode="updates", show_hidden=True)
        self.assertEqual(1, total)
        grouped = items[0]
        self.assertEqual("2026-03-05T00:00:00Z", grouped["newestLocalVersionDate"])
        self.assertEqual(["v-new-2"], [entry["versionId"] for entry in grouped["newVersions"]])
        self.assertEqual(["v-new-1"], [entry["versionId"] for entry in grouped["hiddenNewVersions"]])
        self.assertNotIn("v-old", [entry["versionId"] for entry in grouped["newVersions"]])

        summary = self.manager.summarize_check_items({"mode": "check", "total": 2}, self.job.items)
        self.assertEqual(1, summary["withUpdates"])
        self.assertEqual(1, summary["hiddenUpdates"])

    def test_multi_select_filters_apply_to_grouped_results(self) -> None:
        self.job.items = [
            make_item(
                model_id="m1",
                model_name="Checkpoint One",
                model_type="checkpoint",
                local_version_id="c1",
                local_version_name="c1",
                local_version_date="2026-03-01T00:00:00Z",
                base_model="SDXL 1.0",
                model_path="C:\\models\\c1.safetensors",
                remote_versions=[{
                    "versionId": "c2",
                    "versionName": "c2",
                    "versionDate": "2026-03-02T00:00:00Z",
                    "baseModel": "SDXL 1.0",
                    "previewUrl": "",
                    "previewType": "image",
                    "versionUrl": "",
                    "downloadUrl": "",
                }],
            ),
            make_item(
                model_id="m2",
                model_name="Lora One",
                model_type="lora",
                local_version_id="l1",
                local_version_name="l1",
                local_version_date="2026-03-01T00:00:00Z",
                base_model="Flux.1 D",
                model_path="C:\\models\\l1.safetensors",
                remote_versions=[{
                    "versionId": "l2",
                    "versionName": "l2",
                    "versionDate": "2026-03-03T00:00:00Z",
                    "baseModel": "Flux.1 D",
                    "previewUrl": "",
                    "previewType": "image",
                    "versionUrl": "",
                    "downloadUrl": "",
                }],
            ),
        ]

        total, _, _, items, facets = self.manager.get_items(
            "job-1",
            mode="updates",
            model_types=["lora"],
            base_models=["Flux.1 D"],
        )
        self.assertEqual(1, total)
        self.assertEqual("m2", items[0]["modelId"])
        self.assertEqual(["checkpoint", "lora"], facets["modelTypes"])
        self.assertEqual(["Flux.1 D", "SDXL 1.0"], facets["baseModels"])

    def test_grouping_aggregates_nsfw_flag(self) -> None:
        # Test grouped items
        self.job.items = [
            make_item(
                model_id="m_nsfw",
                model_name="NSFW Model",
                model_type="checkpoint",
                local_version_id="v1",
                local_version_name="v1",
                local_version_date="2026-03-01T00:00:00Z",
                base_model="SDXL 1.0",
                model_path="C:\\models\\nsfw-1.safetensors",
                remote_versions=[],
                nsfw=True,
            ),
            make_item(
                model_id="m_nsfw",
                model_name="NSFW Model",
                model_type="checkpoint",
                local_version_id="v2",
                local_version_name="v2",
                local_version_date="2026-03-02T00:00:00Z",
                base_model="SDXL 1.0",
                model_path="C:\\models\\nsfw-2.safetensors",
                remote_versions=[],
                nsfw=False,
            ),
        ]
        total, _, _, items, _ = self.manager.get_items("job-1")
        self.assertEqual(1, total)
        self.assertTrue(items[0]["nsfw"])

        # Test ungrouped items (no modelId/modelUrl)
        self.job.items = [
            {
                "modelPath": "C:\\models\\unknown.safetensors",
                "modelType": "checkpoint",
                "nsfw": True,
                "localVersionId": "v1",
                "localVersionName": "v1",
                "localVersionDate": "2026-03-01T00:00:00Z",
                "baseModel": "SDXL 1.0",
                "localPreviewUrl": "",
                "localPreviewType": "image",
            }
        ]
        total, _, _, items, _ = self.manager.get_items("job-1")
        self.assertEqual(1, total)
        self.assertTrue(items[0]["nsfw"])


if __name__ == "__main__":
    unittest.main()
