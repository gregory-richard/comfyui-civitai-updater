from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from comfy_updater.civitai_client import CivitaiClient


def _client_streaming(chunks: list[bytes]) -> CivitaiClient:
    client = CivitaiClient(api_key="", timeout_seconds=5, max_retries=0)
    response = MagicMock()
    response.ok = True
    response.iter_content.return_value = iter(chunks)
    response.__enter__.return_value = response
    client.session = MagicMock()
    client.session.get.return_value = response
    return client


class DownloadFileTruncationTests(unittest.TestCase):
    def test_oversized_download_is_rejected_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "preview.png"
            client = _client_streaming([b"a" * 6, b"b" * 6])

            self.assertFalse(client.download_file("https://example.com/x", target, max_bytes=8))
            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix(".png.tmp").exists())

    def test_truncated_head_is_kept_when_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "preview.mp4"
            client = _client_streaming([b"a" * 6, b"b" * 6])

            self.assertTrue(
                client.download_file(
                    "https://example.com/x", target, max_bytes=8, allow_truncated=True
                )
            )
            self.assertEqual(b"aaaaaabb", target.read_bytes())

    def test_complete_download_within_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "preview.png"
            client = _client_streaming([b"a" * 6, b"b" * 6])

            self.assertTrue(client.download_file("https://example.com/x", target, max_bytes=64))
            self.assertEqual(b"a" * 6 + b"b" * 6, target.read_bytes())


if __name__ == "__main__":
    unittest.main()
