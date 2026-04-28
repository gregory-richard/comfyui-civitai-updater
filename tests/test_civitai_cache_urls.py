from __future__ import annotations

import unittest

from comfy_updater.jobs import JobManager


class CivitaiCacheUrlTests(unittest.TestCase):
    def test_cached_civitai_com_page_urls_are_normalized_to_red(self) -> None:
        manager = JobManager()

        record = manager.load_cached_check({
            "checkedAt": "2026-04-28T00:00:00Z",
            "summary": {},
            "items": [{
                "modelId": "6424",
                "modelUrl": "https://civitai.com/models/6424",
                "versionUrl": "https://civitai.com/models/6424?modelVersionId=11745",
                "remoteVersions": [{
                    "versionId": "11745",
                    "versionUrl": "https://civitai.com/models/6424?modelVersionId=11745",
                }],
            }],
        })

        item = record.items[0]
        self.assertEqual("https://civitai.red/models/6424", item["modelUrl"])
        self.assertEqual("https://civitai.red/models/6424?modelVersionId=11745", item["versionUrl"])
        self.assertEqual(
            "https://civitai.red/models/6424?modelVersionId=11745",
            item["remoteVersions"][0]["versionUrl"],
        )


if __name__ == "__main__":
    unittest.main()
