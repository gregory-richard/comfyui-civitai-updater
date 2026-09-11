from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from comfy_updater.archived_updates import ArchivedUpdateStore
from comfy_updater.civitai_client import CivitaiClient, CivitaiRequestError
from comfy_updater.config_store import ConfigStore
from comfy_updater.jobs import _group_items_by_model
from comfy_updater.sidecar import info_sidecar_path, read_json, write_json
from comfy_updater.updater_service import UpdaterService


class _Response:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.reason = {200: "OK", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found"}.get(status_code, "Error")
        self._payload = payload

    def json(self):
        return self._payload


class ClientStrictLookupTests(unittest.TestCase):
    def _client_returning(self, status_code: int) -> CivitaiClient:
        client = CivitaiClient(api_key="", timeout_seconds=5, max_retries=0)
        client.session.get = lambda *args, **kwargs: _Response(status_code)  # type: ignore[assignment]
        return client

    def test_strict_model_lookup_raises_for_missing_model(self) -> None:
        client = self._client_returning(404)
        with self.assertRaises(CivitaiRequestError) as raised:
            client.get_model(6424, raise_on_error=True)
        self.assertIn("404", str(raised.exception))
        # The failure is cached: a second file of the same model gets the same
        # answer without another request.
        client.session.get = lambda *args, **kwargs: self.fail("unexpected request")  # type: ignore[assignment]
        with self.assertRaises(CivitaiRequestError):
            client.get_model(6424, raise_on_error=True)
        self.assertIsNone(client.get_model(6424))

    def test_strict_model_lookup_raises_for_denied_model(self) -> None:
        for status in (401, 403):
            client = self._client_returning(status)
            with self.assertRaises(CivitaiRequestError) as raised:
                client.get_model_versions_for_model(6424)
            self.assertIn(str(status), str(raised.exception))

    def test_lenient_lookup_still_returns_none(self) -> None:
        client = self._client_returning(404)
        self.assertIsNone(client.get_version(11745))


class _MissingModelClient:
    """Model page gone from Civitai: strict lookups raise, as the real client does."""

    def get_version_by_hash(self, sha256_hash):  # noqa: ARG002
        return None

    def get_model_versions_for_model(self, model_id):
        raise CivitaiRequestError(f"https://civitai.red/api/v1/models/{model_id} :: 404 Not Found")

    def model_page_url(self, model_id):
        return f"https://civitai.red/models/{model_id}"

    def version_page_url(self, model_id, version_id=None):
        return f"https://civitai.red/models/{model_id}?modelVersionId={version_id}"


class _DatelessSidecarClient:
    def get_model_versions_for_model(self, model_id):  # noqa: ARG002
        return (
            "artist",
            [
                {"id": 30, "name": "v3", "publishedAt": "2025-01-01T00:00:00Z", "images": []},
                {"id": 20, "name": "v2", "publishedAt": "2024-01-01T00:00:00Z", "images": []},
                {"id": 10, "name": "v1", "publishedAt": "2023-01-01T00:00:00Z", "images": []},
            ],
            False,
        )

    def model_page_url(self, model_id):
        return f"https://civitai.red/models/{model_id}"

    def version_page_url(self, model_id, version_id=None):
        return f"https://civitai.red/models/{model_id}?modelVersionId={version_id}"


class _RecordingHashClient:
    def __init__(self, found: dict | None = None):
        self.hashes: list[str] = []
        self.found = found

    def get_version_by_hash(self, sha256_hash):
        self.hashes.append(sha256_hash)
        return self.found

    def model_page_url(self, model_id):
        return f"https://civitai.red/models/{model_id}"

    def version_page_url(self, model_id, version_id=None):
        return f"https://civitai.red/models/{model_id}?modelVersionId={version_id}"


def _write_model(tmpdir: str, sidecar: dict | None) -> Path:
    model_path = Path(tmpdir) / "example.safetensors"
    model_path.write_bytes(b"not a real model")
    if sidecar is not None:
        write_json(info_sidecar_path(model_path), sidecar)
    return model_path


class UpdaterServiceLookupTests(unittest.TestCase):
    def test_removed_model_is_reported_as_an_error_not_as_up_to_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = _write_model(tmpdir, {"id": 456, "modelId": 123, "name": "Local", "publishedAt": "2024-01-01T00:00:00Z", "images": []})
            item = UpdaterService(None)._process_one(
                client=_MissingModelClient(), model_path=model_path, model_type="lora",
                mode="check", refetch_metadata=False, force_rehash=False,
            )
        self.assertEqual("error", item["status"])
        self.assertIn("404", item["error"])
        self.assertFalse(item["hasUpdate"])

    def test_dateless_sidecar_takes_its_date_from_civitai(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = _write_model(tmpdir, {"id": 20, "modelId": 1, "name": "v2", "images": []})
            item = UpdaterService(None)._process_one(
                client=_DatelessSidecarClient(), model_path=model_path, model_type="lora",
                mode="check", refetch_metadata=False, force_rehash=False,
            )
        self.assertEqual("2024-01-01T00:00:00Z", item["localVersionDate"])
        self.assertTrue(item["hasUpdate"])
        self.assertEqual("30", item["latestVersionId"])

    def test_stub_sidecar_is_retried_with_its_stored_hash(self) -> None:
        stub = {"id": "", "modelId": "", "name": "example.safetensors",
                "files": [{"hashes": {"SHA256": "ABCDEF"}}], "extensions": {"source": "comfy-civitai-updater"}}
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = _write_model(tmpdir, stub)
            client = _RecordingHashClient()
            with patch("comfy_updater.updater_service.sha256_file") as hash_file:
                item = UpdaterService(None)._process_one(
                    client=client, model_path=model_path, model_type="lora",
                    mode="scan", refetch_metadata=False, force_rehash=False,
                )
                hash_file.assert_not_called()
        # Reported honestly as not found instead of hiding behind "skipped".
        self.assertEqual("not_found", item["status"])
        self.assertEqual(["abcdef"], client.hashes)

    def test_stub_sidecar_is_rehashed_when_forced(self) -> None:
        stub = {"id": "", "modelId": "", "files": [{"hashes": {"SHA256": "stale"}}]}
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = _write_model(tmpdir, stub)
            client = _RecordingHashClient()
            with patch("comfy_updater.updater_service.sha256_file", return_value="fresh") as hash_file:
                UpdaterService(None)._process_one(
                    client=client, model_path=model_path, model_type="lora",
                    mode="scan", refetch_metadata=False, force_rehash=True,
                )
                hash_file.assert_called_once()
            self.assertEqual(["fresh"], client.hashes)
            # The stub is rewritten so the fresh hash is what gets reused next time.
            self.assertEqual("fresh", read_json(info_sidecar_path(model_path))["files"][0]["hashes"]["SHA256"])


class GroupingDateTests(unittest.TestCase):
    def _item(self, local_date: str) -> dict:
        return {
            "modelId": "1", "modelType": "lora", "modelName": "M", "modelPath": "a.safetensors",
            "localVersionId": "20", "localVersionName": "v2", "localVersionDate": local_date,
            "remoteVersions": [
                {"versionId": "10", "versionName": "v1", "versionDate": "2023-01-01T00:00:00Z"},
                {"versionId": "20", "versionName": "v2", "versionDate": "2024-01-01T00:00:00Z"},
                {"versionId": "30", "versionName": "v3", "versionDate": "2025-01-01T00:00:00Z"},
            ],
        }

    def test_dateless_local_version_is_backfilled_from_remote_list(self) -> None:
        group = _group_items_by_model([self._item("")])[0]
        self.assertEqual("2024-01-01T00:00:00Z", group["localVersions"][0]["publishedAt"])
        # Only v3 is newer; v1 must not be offered as an update.
        self.assertEqual(["30"], [version["versionId"] for version in group["newVersions"]])

    def test_no_date_at_all_claims_nothing_as_new(self) -> None:
        item = self._item("")
        item["remoteVersions"] = [
            {"versionId": "10", "versionName": "v1", "versionDate": "2023-01-01T00:00:00Z"},
            {"versionId": "30", "versionName": "v3", "versionDate": "2025-01-01T00:00:00Z"},
        ]
        group = _group_items_by_model([item])[0]
        self.assertFalse(group["hasUpdate"])
        self.assertEqual([], group["newVersions"])


class CorruptStoreTests(unittest.TestCase):
    def test_corrupt_config_is_quarantined_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            (data_dir / "config.json").write_text('{"apiKey": "secret", broken', encoding="utf-8")

            store = ConfigStore(data_dir)

            backups = list(data_dir.glob("config.json.corrupt-*"))
            self.assertEqual(1, len(backups))
            self.assertIn("secret", backups[0].read_text(encoding="utf-8"))
            self.assertEqual("", store.get()["apiKey"])
            self.assertIsInstance(json.loads((data_dir / "config.json").read_text(encoding="utf-8")), dict)

    def test_corrupt_archive_is_quarantined_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            (data_dir / "archived_updates.json").write_text('{"archivedUpdates": {"1": ["2"', encoding="utf-8")

            store = ArchivedUpdateStore(data_dir)

            backups = list(data_dir.glob("archived_updates.json.corrupt-*"))
            self.assertEqual(1, len(backups))
            self.assertEqual(set(), store.get_archived_versions("1"))


if __name__ == "__main__":
    unittest.main()
