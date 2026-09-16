"""Testes unitários da ingestão TheAudioDB, sem internet ou AWS."""

import unittest
from unittest.mock import patch

from src.pipeline.ingestion import (
    InvalidIngestionResponseError,
    UsableArtistNotFoundError,
    ingest_theaudiodb_artist,
)
from src.services.theaudiodb.client import TheAudioDBError
from src.storage import S3StorageError


class IngestTheAudioDBArtistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = {
            "artists": [
                {
                    "idArtist": "111279",
                    "strArtist": "Metallica",
                    "strBiographyEN": "Biography",
                }
            ]
        }

    @patch("src.pipeline.ingestion.theaudiodb.save_raw_json")
    @patch("src.pipeline.ingestion.theaudiodb.search_artist")
    def test_ingests_artist_and_returns_reference(self, search, save) -> None:
        search.return_value = self.raw
        save.return_value = "raw/theaudiodb/artists/111279/extraction.json"

        result = ingest_theaudiodb_artist("Metallica")

        search.assert_called_once_with("Metallica")
        self.assertEqual(
            result,
            {
                "artist_name": "Metallica",
                "artist_id": "111279",
                "source": "theaudiodb",
                "raw_s3_key": "raw/theaudiodb/artists/111279/extraction.json",
            },
        )

    @patch("src.pipeline.ingestion.theaudiodb.save_raw_json")
    @patch("src.pipeline.ingestion.theaudiodb.search_artist")
    def test_passes_exact_raw_object_and_storage_arguments(self, search, save) -> None:
        search.return_value = self.raw
        save.return_value = "key"

        ingest_theaudiodb_artist("Metallica")

        args = save.call_args.args
        self.assertEqual(args[0], "theaudiodb")
        self.assertIs(args[1], self.raw)
        self.assertEqual(args[2], "artists")
        self.assertEqual(args[3], "111279")

    @patch("src.pipeline.ingestion.theaudiodb.save_raw_json")
    @patch("src.pipeline.ingestion.theaudiodb.search_artist")
    def test_propagates_invalid_artist_name_from_client(self, search, save) -> None:
        search.side_effect = ValueError("O nome do artista não pode estar vazio.")

        with self.assertRaisesRegex(ValueError, "não pode estar vazio"):
            ingest_theaudiodb_artist("  ")

        save.assert_not_called()

    @patch("src.pipeline.ingestion.theaudiodb.save_raw_json")
    @patch("src.pipeline.ingestion.theaudiodb.search_artist")
    def test_rejects_response_without_artists(self, search, save) -> None:
        search.return_value = {"unexpected": []}

        with self.assertRaisesRegex(InvalidIngestionResponseError, "lista artists"):
            ingest_theaudiodb_artist("Metallica")

        save.assert_not_called()

    @patch("src.pipeline.ingestion.theaudiodb.save_raw_json")
    @patch("src.pipeline.ingestion.theaudiodb.search_artist")
    def test_rejects_empty_artists(self, search, save) -> None:
        search.return_value = {"artists": []}

        with self.assertRaisesRegex(UsableArtistNotFoundError, "idArtist"):
            ingest_theaudiodb_artist("Unknown")

        save.assert_not_called()

    @patch("src.pipeline.ingestion.theaudiodb.save_raw_json")
    @patch("src.pipeline.ingestion.theaudiodb.search_artist")
    def test_rejects_artist_without_id(self, search, save) -> None:
        search.return_value = {"artists": [{"strArtist": "Metallica"}]}

        with self.assertRaisesRegex(UsableArtistNotFoundError, "idArtist"):
            ingest_theaudiodb_artist("Metallica")

        save.assert_not_called()

    @patch("src.pipeline.ingestion.theaudiodb.save_raw_json")
    @patch("src.pipeline.ingestion.theaudiodb.search_artist")
    def test_uses_first_artist_with_usable_id(self, search, save) -> None:
        search.return_value = {
            "artists": [
                {"strArtist": "Invalid"},
                {"idArtist": "222", "strArtist": "Usable"},
                {"idArtist": "333", "strArtist": "Later"},
            ]
        }
        save.return_value = "key"

        result = ingest_theaudiodb_artist("Usable")

        self.assertEqual(result["artist_id"], "222")
        self.assertEqual(save.call_args.args[3], "222")

    @patch("src.pipeline.ingestion.theaudiodb.save_raw_json")
    @patch("src.pipeline.ingestion.theaudiodb.search_artist")
    def test_propagates_client_error_unchanged(self, search, save) -> None:
        original = TheAudioDBError("API indisponível")
        search.side_effect = original

        with self.assertRaises(TheAudioDBError) as raised:
            ingest_theaudiodb_artist("Metallica")

        self.assertIs(raised.exception, original)
        save.assert_not_called()

    @patch("src.pipeline.ingestion.theaudiodb.save_raw_json")
    @patch("src.pipeline.ingestion.theaudiodb.search_artist")
    def test_propagates_storage_error_unchanged(self, search, save) -> None:
        search.return_value = self.raw
        original = S3StorageError("S3 indisponível")
        save.side_effect = original

        with self.assertRaises(S3StorageError) as raised:
            ingest_theaudiodb_artist("Metallica")

        self.assertIs(raised.exception, original)


if __name__ == "__main__":
    unittest.main()
