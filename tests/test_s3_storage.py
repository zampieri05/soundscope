"""Testes unitários da persistência RAW no S3, sem acesso à AWS."""

import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

from src.storage import S3StorageError, save_raw_json


class SaveRawJsonTests(unittest.TestCase):
    BUCKET = "bucket-de-teste"
    EXTRACTED_AT = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)

    def setUp(self):
        self.client = Mock()
        self.bucket = patch.dict(
            os.environ, {"SOUNDSCOPE_S3_BUCKET": self.BUCKET}, clear=False
        )
        self.bucket.start()

    def tearDown(self):
        self.bucket.stop()

    def _save(self, source, data, entity_type, entity_id):
        return save_raw_json(
            source,
            data,
            entity_type,
            entity_id,
            s3_client=self.client,
            extracted_at=self.EXTRACTED_AT,
        )

    def test_stores_theaudiodb_raw_with_expected_bucket_key_and_json(self):
        raw = {"artists": [{"idArtist": "123", "strArtist": "Björk"}]}

        key = self._save("theaudiodb", raw, "artists", "123")

        self.assertEqual(
            key, "raw/theaudiodb/artists/123/20260910T150000000000Z.json"
        )
        call = self.client.put_object.call_args.kwargs
        self.assertEqual(call["Bucket"], self.BUCKET)
        self.assertEqual(call["Key"], key)
        self.assertEqual(call["ContentType"], "application/json")
        self.assertEqual(json.loads(call["Body"].decode("utf-8")), raw)
        self.assertIn('"strArtist"', call["Body"].decode("utf-8"))

    def test_stores_musicbrainz_raw_and_returns_key(self):
        raw = {"id": "mbid-1", "name": "Massive Attack", "tags": [{"x": 1}]}

        key = self._save("musicbrainz", raw, "artists", "mbid-1")

        self.assertEqual(
            key, "raw/musicbrainz/artists/mbid-1/20260910T150000000000Z.json"
        )
        stored = json.loads(self.client.put_object.call_args.kwargs["Body"])
        self.assertEqual(stored, raw)

    def test_escapes_entity_id_in_key(self):
        key = self._save("theaudiodb", {"album": []}, "albums", "artist/42")
        self.assertIn("/artist%2F42/", key)

    def test_rejects_invalid_source(self):
        with self.assertRaisesRegex(S3StorageError, "source inválida"):
            self._save("spotify", {}, "artists", "123")
        self.client.put_object.assert_not_called()

    def test_rejects_invalid_entity_type(self):
        with self.assertRaisesRegex(S3StorageError, "entity_type inválido"):
            self._save("musicbrainz", {}, "albums", "123")

    def test_rejects_empty_entity_id(self):
        with self.assertRaisesRegex(S3StorageError, "entity_id"):
            self._save("theaudiodb", {}, "artists", "  ")

    def test_requires_configured_bucket(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(S3StorageError, "SOUNDSCOPE_S3_BUCKET"):
                self._save("theaudiodb", {}, "artists", "123")
        self.client.put_object.assert_not_called()

    def test_rejects_invalid_or_non_serializable_raw(self):
        with self.assertRaisesRegex(S3StorageError, "objeto ou lista"):
            self._save("theaudiodb", None, "artists", "123")
        with self.assertRaisesRegex(S3StorageError, "não é serializável"):
            self._save("theaudiodb", {"invalid": object()}, "artists", "123")

    def test_wraps_s3_client_error_with_original_cause(self):
        original = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "PutObject"
        )
        self.client.put_object.side_effect = original

        with self.assertRaisesRegex(S3StorageError, "Falha ao salvar") as raised:
            self._save("theaudiodb", {}, "artists", "123")

        self.assertIs(raised.exception.__cause__, original)

    @patch("src.storage.s3.boto3.client")
    def test_creates_client_lazily_and_does_not_call_external_apis(self, boto_client):
        boto_client.return_value = self.client
        with patch("requests.sessions.Session.request") as http_request:
            save_raw_json(
                "musicbrainz",
                {"id": "mbid-1"},
                "artists",
                "mbid-1",
                extracted_at=self.EXTRACTED_AT,
            )

        boto_client.assert_called_once_with("s3")
        http_request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
