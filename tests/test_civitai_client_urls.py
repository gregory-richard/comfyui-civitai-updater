from __future__ import annotations

import unittest

from comfy_updater.civitai_client import CivitaiClient
from comfy_updater.constants import (
    MODEL_BY_ID_URL,
    MODEL_VERSION_BY_ID_URL,
    PLUGIN_VERSION,
    USER_AGENT,
    VERSION_BY_HASH_URL,
)


class CivitaiClientUrlTests(unittest.TestCase):
    def test_api_urls_use_civitai_red(self) -> None:
        # civitai.com API responses are SFW-filtered since the April 2026
        # domain split; only civitai.red serves the full catalog.
        self.assertEqual("https://civitai.red/api/v1/model-versions/by-hash", VERSION_BY_HASH_URL)
        self.assertEqual("https://civitai.red/api/v1/models", MODEL_BY_ID_URL)
        self.assertEqual("https://civitai.red/api/v1/model-versions", MODEL_VERSION_BY_ID_URL)

    def test_page_urls_always_use_civitai_red(self) -> None:
        client = CivitaiClient(api_key="", timeout_seconds=30, max_retries=0)
        self.assertEqual("https://civitai.red/models/6424", client.model_page_url(6424))
        self.assertEqual(
            "https://civitai.red/models/6424?modelVersionId=11745",
            client.version_page_url(6424, 11745),
        )
        self.assertEqual("https://civitai.red/models/6424", client.version_page_url(6424, None))

    def test_user_agent_carries_the_release_version(self) -> None:
        # The version is read from pyproject.toml so it cannot drift from the
        # published release the way a hard-coded string did.
        self.assertNotEqual("unknown", PLUGIN_VERSION)
        self.assertEqual(f"comfyui-civitai-updater/{PLUGIN_VERSION}", USER_AGENT)
        client = CivitaiClient(api_key="", timeout_seconds=30, max_retries=0)
        self.assertEqual(USER_AGENT, client.default_headers["User-Agent"])


if __name__ == "__main__":
    unittest.main()
