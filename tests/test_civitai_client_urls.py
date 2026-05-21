from __future__ import annotations

import unittest

from comfy_updater.civitai_client import CivitaiClient
from comfy_updater.constants import MODEL_BY_ID_URL, MODEL_VERSION_BY_ID_URL, VERSION_BY_HASH_URL


class CivitaiClientUrlTests(unittest.TestCase):
    def test_api_urls_remain_on_civitai_com(self) -> None:
        self.assertEqual("https://civitai.com/api/v1/model-versions/by-hash", VERSION_BY_HASH_URL)
        self.assertEqual("https://civitai.com/api/v1/models", MODEL_BY_ID_URL)
        self.assertEqual("https://civitai.com/api/v1/model-versions", MODEL_VERSION_BY_ID_URL)

    def test_page_urls_use_default_civitai_com(self) -> None:
        client = CivitaiClient(api_key="", timeout_seconds=30, max_retries=0)

        self.assertEqual("https://civitai.com/models/6424", client.model_page_url(6424))
        self.assertEqual(
            "https://civitai.com/models/6424?modelVersionId=11745",
            client.version_page_url(6424, 11745),
        )

    def test_page_urls_can_use_configured_civitai_red(self) -> None:
        client = CivitaiClient(api_key="", timeout_seconds=30, max_retries=0, civitai_domain="civitai.red")

        self.assertEqual("https://civitai.red/models/6424", client.model_page_url(6424))
        self.assertEqual(
            "https://civitai.red/models/6424?modelVersionId=11745",
            client.version_page_url(6424, 11745),
        )


if __name__ == "__main__":
    unittest.main()
