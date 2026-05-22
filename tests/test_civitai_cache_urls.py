from __future__ import annotations

import unittest

from comfy_updater.jobs import JobManager


class MockConfigStore:
    def __init__(self, domain: str = "civitai.red"):
        self.domain = domain

    def get(self) -> dict:
        return {"civitaiDomain": self.domain}


class CivitaiCacheUrlTests(unittest.TestCase):
    def test_cached_civitai_urls_are_normalized_to_default_domain(self) -> None:
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

    def test_cached_civitai_urls_are_normalized_to_civitai_red_regardless_of_config(self) -> None:
        mock_config = MockConfigStore("civitai.com")
        manager = JobManager(config_store=mock_config)

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

    def test_cached_civitai_urls_normalize_to_civitai_red_when_nsfw(self) -> None:
        mock_config = MockConfigStore("civitai.com")
        manager = JobManager(config_store=mock_config)

        record = manager.load_cached_check({
            "checkedAt": "2026-04-28T00:00:00Z",
            "summary": {},
            "items": [{
                "modelId": "6424",
                "modelUrl": "https://civitai.com/models/6424",
                "versionUrl": "https://civitai.com/models/6424?modelVersionId=11745",
                "nsfw": True,
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
