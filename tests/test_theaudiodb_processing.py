"""Testes do pipeline processado, sem chamadas externas."""

import unittest
from unittest.mock import Mock, call, patch

from src.models import NormalizedArtist
from src.pipeline.processing import process_theaudiodb_artist
from src.pipeline.transformers.errors import TransformationError
from src.storage import S3StorageError


class ProcessTheAudioDBArtistTests(unittest.TestCase):
    def setUp(self):
        self.raw = {
            "artists": [{"idArtist": "111279", "strArtist": "Metallica"}]
        }
        self.normalized = NormalizedArtist(
            source="theaudiodb", source_artist_id="111279", name="Metallica"
        )

    @patch("src.pipeline.processing.theaudiodb.save_processed_json")
    @patch("src.pipeline.processing.theaudiodb.transform_theaudiodb_artist")
    @patch("src.pipeline.processing.theaudiodb.save_raw_json")
    @patch("src.pipeline.processing.theaudiodb.search_artist")
    def test_complete_flow_preserves_raw_and_serializes_model(
        self, search, save_raw, transform, save_processed
    ):
        search.return_value = self.raw
        save_raw.return_value = "raw-key"
        transform.return_value = self.normalized
        save_processed.return_value = "processed-key"

        result = process_theaudiodb_artist("Metallica")

        search.assert_called_once_with("Metallica")
        save_raw.assert_called_once_with(
            "theaudiodb", self.raw, "artists", "111279"
        )
        self.assertIs(save_raw.call_args.args[1], self.raw)
        transform.assert_called_once_with(self.raw)
        save_processed.assert_called_once_with(
            {
                "source": "theaudiodb",
                "source_artist_id": "111279",
                "name": "Metallica",
                "country": None,
                "genre": None,
                "formed_year": None,
                "biography": None,
                "image_url": None,
            },
            "artists",
            "111279",
        )
        self.assertEqual(
            result,
            {
                "artist_name": "Metallica",
                "artist_id": "111279",
                "source": "theaudiodb",
                "raw_s3_key": "raw-key",
                "processed_s3_key": "processed-key",
            },
        )

    @patch("src.pipeline.processing.theaudiodb.save_processed_json")
    @patch("src.pipeline.processing.theaudiodb.transform_theaudiodb_artist")
    @patch("src.pipeline.processing.theaudiodb.save_raw_json")
    @patch("src.pipeline.processing.theaudiodb.search_artist")
    def test_saves_raw_before_transforming(
        self, search, save_raw, transform, save_processed
    ):
        timeline = Mock()
        search.return_value = self.raw
        save_raw.return_value = "raw-key"
        transform.return_value = self.normalized
        save_processed.return_value = "processed-key"
        timeline.attach_mock(save_raw, "raw")
        timeline.attach_mock(transform, "transform")
        timeline.attach_mock(save_processed, "processed")

        process_theaudiodb_artist("Metallica")

        self.assertEqual(
            [entry[0] for entry in timeline.mock_calls],
            ["raw", "transform", "processed"],
        )

    def test_failures_are_propagated_and_stop_later_stages(self):
        stages = ("search_artist", "save_raw_json", "transform_theaudiodb_artist", "save_processed_json")
        errors = (
            ValueError("extração falhou"),
            S3StorageError("raw falhou"),
            TransformationError("transformação falhou"),
            S3StorageError("processed falhou"),
        )
        for failed_index, original in enumerate(errors):
            mocks = {
                "search_artist": Mock(return_value=self.raw),
                "save_raw_json": Mock(return_value="raw-key"),
                "transform_theaudiodb_artist": Mock(return_value=self.normalized),
                "save_processed_json": Mock(return_value="processed-key"),
            }
            with self.subTest(stage=stages[failed_index]), patch.multiple(
                "src.pipeline.processing.theaudiodb",
                **mocks,
            ):
                mocks[stages[failed_index]].side_effect = original
                with self.assertRaises(type(original)) as raised:
                    process_theaudiodb_artist("Metallica")
                self.assertIs(raised.exception, original)
                for later_stage in stages[failed_index + 1 :]:
                    mocks[later_stage].assert_not_called()


if __name__ == "__main__":
    unittest.main()
