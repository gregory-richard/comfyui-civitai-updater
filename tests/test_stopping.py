from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from comfy_updater.civitai_client import CivitaiClient
from comfy_updater.config_store import ConfigStore
from comfy_updater.hashing import HashingCancelled, sha256_file
from comfy_updater.updater_service import UpdaterService


class _Response:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.reason = "Service Unavailable"


class _StopAfter:
    """A job control that reports Stop once it has been asked ``calls`` times."""

    def __init__(self, calls: int):
        self.calls = calls

    def wait_if_paused(self) -> None:
        pass

    def is_cancelled(self) -> bool:
        self.calls -= 1
        return self.calls < 0


class StopTests(unittest.TestCase):
    def test_hashing_stops_when_asked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "big.safetensors"
            path.write_bytes(b"x" * 16)
            with self.assertRaises(HashingCancelled):
                sha256_file(path, chunk_size=4, should_stop=_StopAfter(2).is_cancelled)

    def test_retries_stop_when_asked(self) -> None:
        client = CivitaiClient(api_key="", timeout_seconds=5, max_retries=4, should_stop=lambda: True)
        requests: list[str] = []
        client.session.get = lambda url, **kwargs: requests.append(url) or _Response(503)  # type: ignore[assignment]
        with patch("comfy_updater.civitai_client.time.sleep") as sleep:
            self.assertIsNone(client.get_version(1))
            sleep.assert_not_called()
        self.assertEqual(1, len(requests))

    def test_stop_during_a_hash_reports_nothing_for_that_file(self) -> None:
        with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as models_dir:
            (Path(models_dir) / "model.safetensors").write_bytes(b"weights")
            config = ConfigStore(Path(data_dir))
            config.update({
                "useComfyPaths": False,
                "useExtraModelPaths": False,
                "requestDelayMs": 0,
                "customPaths": {"lora": [models_dir]},
            })
            emitted: list[dict] = []

            # Asked once before the file (not stopped), then inside the hash.
            summary, items = UpdaterService(config).run_check_updates(
                {"modelTypes": ["lora"], "includeCustomPaths": True},
                lambda *args: None,
                emitted.append,
                _StopAfter(1),
            )

        self.assertEqual([], items)
        self.assertEqual([], emitted)
        self.assertEqual(1, summary["total"])


if __name__ == "__main__":
    unittest.main()
