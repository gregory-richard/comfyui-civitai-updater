from __future__ import annotations

import unittest

from comfy_updater.civitai_client import CivitaiClient
from comfy_updater.constants import MODEL_BY_ID_URL, MODEL_VERSION_BY_ID_URL, VERSION_BY_HASH_URL


class CivitaiClientUrlTests(unittest.TestCase):
    def test_api_urls_use_civitai_red(self) -> None:
        # civitai.com API responses are SFW-filtered since the April 2026
        # domain split; only civitai.red serves the full catalog.
        self.assertEqual("https://civitai.red/api/v1/model-versions/by-hash", VERSION_BY_HASH_URL)
        self.assertEqual("https://civitai.red/api/v1/models", MODEL_BY_ID_URL)
        self.assertEqual("https://civitai.red/api/v1/model-versions", MODEL_VERSION_BY_ID_URL)

    def test_page_urls_always_use_civitai_red(self) -> None:
        # Test default initialization
        client = CivitaiClient(api_key="", timeout_seconds=30, max_retries=0)
        self.assertEqual("https://civitai.red/models/6424", client.model_page_url(6424))
        self.assertEqual(
            "https://civitai.red/models/6424?modelVersionId=11745",
            client.version_page_url(6424, 11745),
        )

        # Test when passing civitai_domain parameter - should be ignored
        client_with_domain = CivitaiClient(api_key="", timeout_seconds=30, max_retries=0, civitai_domain="civitai.com")
        self.assertEqual("https://civitai.red/models/6424", client_with_domain.model_page_url(6424))
        self.assertEqual(
            "https://civitai.red/models/6424?modelVersionId=11745",
            client_with_domain.version_page_url(6424, 11745),
        )

    def test_page_urls_remain_civitai_red_when_nsfw(self) -> None:
        client = CivitaiClient(api_key="", timeout_seconds=30, max_retries=0)

        self.assertEqual("https://civitai.red/models/6424", client.model_page_url(6424, nsfw=True))
        self.assertEqual(
            "https://civitai.red/models/6424?modelVersionId=11745",
            client.version_page_url(6424, 11745, nsfw=True),
        )


if __name__ == "__main__":
    unittest.main()
