from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from comfy_updater.archived_updates import ArchivedUpdateStore
from comfy_updater.base_models import UNKNOWN_FAMILY, base_family
from comfy_updater.jobs import JobManager, JobRecord


def item(model_id, name, model_type, base, nsfw=False, new_bases=None, local_date="2024-01-01T00:00:00Z"):
    """One local file with optional newer remote releases."""
    remote = []
    for index, new_base in enumerate(new_bases or []):
        remote.append({
            "versionId": f"{model_id}-n{index}",
            "versionName": f"new {index}",
            "versionDate": f"2025-0{index + 1}-01T00:00:00Z",
            "baseModel": new_base,
            "previewUrl": "",
            "previewType": "image",
            "versionUrl": "",
            "downloadUrl": "",
        })
    return {
        "modelId": model_id,
        "modelName": name,
        "modelType": model_type,
        "creatorName": "artist",
        "modelUrl": f"https://civitai.red/models/{model_id}",
        "modelPath": f"C:\\models\\{model_id}.safetensors",
        "baseModel": base,
        "localVersionId": f"{model_id}-local",
        "localVersionName": "local",
        "localVersionDate": local_date,
        "localPreviewUrl": "",
        "localPreviewType": "image",
        "remoteVersions": remote,
        "hasUpdate": bool(remote),
        "status": "ok",
        "nsfw": nsfw,
    }


class BaseFamilyTests(unittest.TestCase):
    def test_real_library_values_roll_up(self) -> None:
        cases = {
            "Flux.1 D": "Flux",
            "Flux.2 Klein 9B": "Flux",
            "Flux.2 Klein 9B-base": "Flux",
            "Wan Video": "Wan",
            "Wan Video 2.2 I2V-A14B": "Wan",
            "SDXL 1.0": "SDXL",
            "SDXL Lightning": "SDXL",
            "ZImageTurbo": "Z-Image",
            "ZImageBase": "Z-Image",
            "LTXV2": "LTXV",
            "LTXV 2.3": "LTXV",
            "SD 1.5": "SD 1.5",
            "Pony": "Pony",
            "Illustrious": "Illustrious",
            "NoobAI": "NoobAI",
        }
        for value, family in cases.items():
            self.assertEqual(family, base_family(value), value)

    def test_unknown_values_are_kept_verbatim(self) -> None:
        # A base model invented next month must get its own group rather than
        # disappearing into a catch-all.
        self.assertEqual("Brand New Model 9", base_family("Brand New Model 9"))
        self.assertEqual(UNKNOWN_FAMILY, base_family(""))
        self.assertEqual(UNKNOWN_FAMILY, base_family(None))


class GroupingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.manager = JobManager(ArchivedUpdateStore(Path(self.tmpdir.name)))
        self.job = JobRecord(id="job-1", type="check-updates", status="completed")
        self.manager._jobs["job-1"] = self.job

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_two_level_grouping_orders_types_then_families(self) -> None:
        self.job.items = [
            item("m1", "Lora A", "lora", "Flux.1 D", new_bases=["Flux.1 D"]),
            item("m2", "Check A", "checkpoint", "SDXL 1.0", new_bases=["SDXL 1.0"]),
            item("m3", "Check B", "checkpoint", "Flux.2 Klein 9B", new_bases=["Flux.2 Klein 9B"]),
        ]

        result = self.manager.get_items(
            "job-1", mode="updates", group_by="type", then_by="baseFamily", limit=50
        )

        # Checkpoints come before LoRA, matching how the library is organised.
        self.assertEqual(["Checkpoint", "Lora"], [g["label"] for g in result["groups"]])
        checkpoint = result["groups"][0]
        self.assertEqual(2, checkpoint["models"])
        self.assertEqual(2, checkpoint["releases"])
        self.assertEqual(["Flux", "SDXL"], [s["label"] for s in checkpoint["subgroups"]])
        # Every card carries the group it belongs to.
        self.assertEqual(
            [("Checkpoint", "Flux"), ("Checkpoint", "SDXL"), ("Lora", "Flux")],
            [(c["groupPrimary"], c["groupSecondary"]) for c in result["items"]],
        )

    def test_card_is_filed_under_the_base_of_its_newest_release(self) -> None:
        # Local file is SDXL 1.0 but the newest release is Flux: the card is
        # filed under what is waiting for you, not what you already have.
        self.job.items = [item("m1", "Mixed", "checkpoint", "SDXL 1.0", new_bases=["Flux.1 D"])]

        result = self.manager.get_items("job-1", mode="updates", group_by="baseFamily", limit=50)

        self.assertEqual("Flux", result["items"][0]["groupPrimary"])
        self.assertEqual("Flux", result["items"][0]["baseFamily"])

    def test_group_counts_cover_every_page_not_just_this_one(self) -> None:
        self.job.items = [
            item(f"m{i}", f"Model {i}", "checkpoint", "SDXL 1.0", new_bases=["SDXL 1.0"])
            for i in range(7)
        ]

        page2 = self.manager.get_items(
            "job-1", mode="updates", group_by="type", then_by="none", offset=3, limit=3
        )

        self.assertEqual(7, page2["total"])
        self.assertEqual(7, page2["groups"][0]["models"])
        self.assertEqual(3, len(page2["items"]))
        # The group started before this page, so the header repeats as "cont."
        self.assertTrue(page2["startsMidPrimary"])

    def test_first_page_is_not_a_continuation(self) -> None:
        self.job.items = [
            item(f"m{i}", f"Model {i}", "checkpoint", "SDXL 1.0", new_bases=["SDXL 1.0"])
            for i in range(4)
        ]

        page1 = self.manager.get_items(
            "job-1", mode="updates", group_by="type", offset=0, limit=2
        )

        self.assertFalse(page1["startsMidPrimary"])

    def test_collapsed_group_drops_its_cards_but_keeps_its_counts(self) -> None:
        self.job.items = [
            item("m1", "Check A", "checkpoint", "SDXL 1.0", new_bases=["SDXL 1.0"]),
            item("m2", "Lora A", "lora", "SDXL 1.0", new_bases=["SDXL 1.0"]),
        ]

        result = self.manager.get_items(
            "job-1", mode="updates", group_by="type", collapsed=["Checkpoint"], limit=50
        )

        self.assertEqual(1, result["total"])
        self.assertEqual("Lora", result["items"][0]["groupPrimary"])
        self.assertEqual(
            {"Checkpoint": 1, "Lora": 1},
            {g["label"]: g["models"] for g in result["groups"]},
        )

    def test_mature_hide_filters_and_reports_the_count(self) -> None:
        self.job.items = [
            item("m1", "Safe", "checkpoint", "SDXL 1.0", new_bases=["SDXL 1.0"]),
            item("m2", "Mature", "checkpoint", "SDXL 1.0", nsfw=True, new_bases=["SDXL 1.0"]),
        ]

        hidden = self.manager.get_items("job-1", mode="updates", mature="hide", limit=50)
        shown = self.manager.get_items("job-1", mode="updates", mature="show", limit=50)

        self.assertEqual(1, hidden["total"])
        self.assertEqual(1, hidden["matureHidden"])
        self.assertEqual("Safe", hidden["items"][0]["modelName"])
        # Blur is a display choice, so it must not remove anything.
        self.assertEqual(2, shown["total"])
        self.assertEqual(0, shown["matureHidden"])

    def test_furthest_behind_sort_leads_with_the_biggest_gap(self) -> None:
        self.job.items = [
            item("m1", "Recent", "checkpoint", "SDXL 1.0",
                 new_bases=["SDXL 1.0"], local_date="2024-12-01T00:00:00Z"),
            item("m2", "Ancient", "checkpoint", "SDXL 1.0",
                 new_bases=["SDXL 1.0"], local_date="2020-01-01T00:00:00Z"),
        ]

        result = self.manager.get_items("job-1", mode="updates", sort="behind", limit=50)

        self.assertEqual(["Ancient", "Recent"], [c["modelName"] for c in result["items"]])
        self.assertGreater(result["items"][0]["daysBehind"], result["items"][1]["daysBehind"])

    def test_grouping_off_leaves_a_flat_list(self) -> None:
        self.job.items = [item("m1", "A", "checkpoint", "SDXL 1.0", new_bases=["SDXL 1.0"])]

        result = self.manager.get_items("job-1", mode="updates", group_by="none", limit=50)

        self.assertEqual([], result["groups"])
        self.assertEqual("", result["items"][0]["groupPrimary"])


if __name__ == "__main__":
    unittest.main()
