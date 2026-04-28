from __future__ import annotations

import unittest

from comfy_updater.routes import _normalize_archive_payload
from comfy_updater.updater_service import _version_date


class RouteAndVersionHelperTests(unittest.TestCase):
    def test_normalize_archive_payload(self) -> None:
        model_id, version_ids = _normalize_archive_payload({
            "modelId": 42,
            "versionIds": ["a", "b", "a", "", None],
        })
        self.assertEqual("42", model_id)
        self.assertEqual(["a", "b"], version_ids)

    def test_version_date_prefers_published_and_falls_back_to_created(self) -> None:
        self.assertEqual(
            "2026-03-10T00:00:00Z",
            _version_date({"publishedAt": "2026-03-10T00:00:00Z", "createdAt": "2026-03-01T00:00:00Z"}),
        )
        self.assertEqual(
            "2026-03-01T00:00:00Z",
            _version_date({"publishedAt": "", "createdAt": "2026-03-01T00:00:00Z"}),
        )


if __name__ == "__main__":
    unittest.main()
