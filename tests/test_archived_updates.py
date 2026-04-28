from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from comfy_updater.archived_updates import ArchivedUpdateStore


class ArchivedUpdateStoreTests(unittest.TestCase):
    def test_archive_and_restore_persist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArchivedUpdateStore(Path(tmpdir))
            archived = store.archive("123", ["456", "789", "456"])
            self.assertEqual(["456", "789"], archived)
            self.assertEqual({"456", "789"}, store.get_archived_versions("123"))

            reloaded = ArchivedUpdateStore(Path(tmpdir))
            self.assertEqual({"456", "789"}, reloaded.get_archived_versions("123"))

            remaining = reloaded.restore("123", ["456"])
            self.assertEqual(["789"], remaining)
            self.assertEqual({"789"}, reloaded.get_archived_versions("123"))


if __name__ == "__main__":
    unittest.main()
