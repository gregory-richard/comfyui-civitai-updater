from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from comfy_updater.archived_updates import ArchivedUpdateStore
from comfy_updater.jobs import JobManager, JobRecord
from comfy_updater.updater_service import _normalize_remote_versions


class FakeCivitaiClient:
    def version_page_url(self, model_id, version_id, nsfw=False):  # noqa: ARG002
        return f"https://example.com/models/{model_id}?modelVersionId={version_id}"


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
    metadata_only: bool = False,
) -> dict:
    primary = remote_versions[0] if remote_versions else {}
    return {
        "modelId": model_id,
        "modelName": model_name,
        "modelType": model_type,
        "creatorName": "artist",
        "modelUrl": f"https://civitai.com/models/{model_id}",
        "modelPath": model_path,
        "metadataOnly": metadata_only,
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

    def test_remote_version_normalization_preserves_availability(self) -> None:
        versions = _normalize_remote_versions(
            FakeCivitaiClient(),
            "m1",
            [
                {
                    "id": "v1",
                    "name": "Paid Window",
                    "publishedAt": "2026-03-07T00:00:00Z",
                    "baseModel": "SDXL 1.0",
                    "availability": "EarlyAccess",
                    "downloadUrl": "https://example.com/download/v1",
                }
            ],
        )

        self.assertEqual("EarlyAccess", versions[0]["availability"])

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
                "availability": "EarlyAccess",
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
                "availability": "Public",
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
                model_path="C:\\models\\one-a.civitai.info",
                remote_versions=remote_versions,
                metadata_only=True,
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

        result = self.manager.get_items("job-1", mode="updates", show_hidden=True)
        self.assertEqual(1, result["total"])
        grouped = result["items"][0]
        self.assertEqual("2026-03-05T00:00:00Z", grouped["newestLocalVersionDate"])
        self.assertEqual(["v-new-2"], [entry["versionId"] for entry in grouped["newVersions"]])
        self.assertEqual(["v-new-1"], [entry["versionId"] for entry in grouped["hiddenNewVersions"]])
        self.assertEqual("EarlyAccess", grouped["newVersions"][0]["availability"])
        self.assertEqual("EarlyAccess", grouped["latestAvailability"])
        self.assertTrue(grouped["localVersions"][1]["metadataOnly"])
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

        result = self.manager.get_items(
            "job-1",
            mode="updates",
            model_types=["lora"],
            base_models=["Flux.1 D"],
        )
        self.assertEqual(1, result["total"])
        self.assertEqual("m2", result["items"][0]["modelId"])
        self.assertEqual(["checkpoint", "lora"], result["facets"]["modelTypes"])
        self.assertEqual(["Flux.1 D", "SDXL 1.0"], result["facets"]["baseModels"])

    def test_start_refuses_second_concurrent_job(self) -> None:
        import threading

        release = threading.Event()
        started = threading.Event()

        def runner(progress, item_cb, control):  # noqa: ARG001
            started.set()
            release.wait(timeout=5)
            return {}, []

        first = self.manager.start("scan", runner)
        self.assertIsNotNone(first)
        self.assertTrue(started.wait(timeout=5))

        second = self.manager.start("scan", runner)
        self.assertIsNone(second)

        release.set()

    def test_seeded_items_are_replaced_when_fresh_results_arrive(self) -> None:
        import threading
        import time as time_module

        seeded = [
            {"modelPath": "C:\\models\\a.safetensors", "modelId": "m1", "_seeded": True},
            {"modelPath": "C:\\models\\b.safetensors", "modelId": "m2", "_seeded": True},
        ]
        fresh_a = {"modelPath": "C:\\models\\A.safetensors", "modelId": "m1", "status": "ok"}
        emitted = threading.Event()
        release = threading.Event()

        def runner(progress, item_cb, control):  # noqa: ARG001
            item_cb(fresh_a)
            emitted.set()
            release.wait(timeout=5)
            return {}, [fresh_a]

        job = self.manager.start("check-updates", runner, seed_items=seeded)
        self.assertIsNotNone(job)
        self.assertTrue(emitted.wait(timeout=5))

        with self.manager._lock:
            paths = [item["modelPath"] for item in job.items]
        # The fresh item replaces its seeded counterpart (case-insensitive),
        # while untouched seeds keep showing.
        self.assertIn("C:\\models\\A.safetensors", paths)
        self.assertNotIn("C:\\models\\a.safetensors", paths)
        self.assertIn("C:\\models\\b.safetensors", paths)

        release.set()
        for _ in range(100):
            if job.status == "completed":
                break
            time_module.sleep(0.05)
        self.assertEqual("completed", job.status)
        # Completion keeps only the fresh results.
        self.assertEqual([fresh_a], job.items)

    def test_cancel_keeps_unreplaced_seeded_items(self) -> None:
        import threading
        import time as time_module

        seeded = [
            {"modelPath": "C:\\models\\a.safetensors", "modelId": "m1", "_seeded": True},
            {"modelPath": "C:\\models\\b.safetensors", "modelId": "m2", "_seeded": True},
        ]
        fresh_a = {"modelPath": "C:\\models\\a.safetensors", "modelId": "m1", "status": "ok"}
        emitted = threading.Event()
        release = threading.Event()

        def runner(progress, item_cb, control):  # noqa: ARG001
            item_cb(fresh_a)
            emitted.set()
            release.wait(timeout=5)
            return {"partial": True}, [fresh_a]

        job = self.manager.start("check-updates", runner, seed_items=seeded)
        self.assertIsNotNone(job)
        self.assertTrue(emitted.wait(timeout=5))

        self.manager.cancel(job.id)
        release.set()
        for _ in range(100):
            if job.status == "cancelled":
                break
            time_module.sleep(0.05)
        self.assertEqual("cancelled", job.status)

        # The unreplaced seed survives the cancel; the fresh result stays.
        paths = sorted(item["modelPath"] for item in job.items)
        self.assertEqual(
            ["C:\\models\\a.safetensors", "C:\\models\\b.safetensors"],
            paths,
        )
        fresh = [item for item in job.items if not item.get("_seeded")]
        self.assertEqual([fresh_a], fresh)

    def test_finished_jobs_are_pruned(self) -> None:
        from comfy_updater import jobs as jobs_module

        for index in range(jobs_module._MAX_FINISHED_JOBS + 3):
            record = JobRecord(
                id=f"finished-{index}",
                type="check-updates",
                status="completed",
                finishedAt=f"2026-01-{index + 1:02d}T00:00:00Z",
            )
            self.manager._jobs[record.id] = record

        def runner(progress, item_cb, control):  # noqa: ARG001
            return {}, []

        job = self.manager.start("scan", runner)
        self.assertIsNotNone(job)

        # Only the newest _MAX_FINISHED_JOBS finished jobs survive the prune.
        remaining = [job_id for job_id in self.manager._jobs if job_id.startswith("finished-")]
        self.assertEqual(
            [f"finished-{index}" for index in range(3, 8)],
            sorted(remaining),
        )
        self.assertNotIn("job-1", self.manager._jobs)

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
        result = self.manager.get_items("job-1")
        self.assertEqual(1, result["total"])
        self.assertTrue(result["items"][0]["nsfw"])

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
        result = self.manager.get_items("job-1")
        self.assertEqual(1, result["total"])
        self.assertTrue(result["items"][0]["nsfw"])


if __name__ == "__main__":
    unittest.main()
