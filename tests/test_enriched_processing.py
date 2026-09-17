"""Testes do pipeline multi-source, sem internet ou AWS."""

import unittest
from unittest.mock import Mock, call, patch

from src.models import EnrichedArtist, NormalizedArtist
from src.pipeline.processing import process_enriched_artist
from src.services.musicbrainz.client import ArtistNotFoundError, MusicBrainzError


MODULE = "src.pipeline.processing.enriched"


class ProcessEnrichedArtistTests(unittest.TestCase):
    def setUp(self):
        self.tadb_raw = {
            "artists": [{"idArtist": "111279", "strArtist": "Metallica"}]
        }
        self.mb_search = {
            "artists": [None, {"id": "mbid-1", "name": "Metallica"}]
        }
        self.mb_details = {"id": "mbid-1", "name": "Metallica", "country": "US"}
        self.tadb_normalized = NormalizedArtist(
            "theaudiodb", "111279", "Metallica", genre="Metal"
        )
        self.mb_normalized = NormalizedArtist(
            "musicbrainz", "mbid-1", "Metallica", country="US"
        )
        self.enriched = EnrichedArtist(
            name="Metallica",
            country="US",
            genre="Metal",
            formed_year=None,
            biography=None,
            image_url=None,
            source_ids={"theaudiodb": "111279", "musicbrainz": "mbid-1"},
        )

    def _mocks(self):
        return {
            "theaudiodb_client": Mock(
                search_artist=Mock(return_value=self.tadb_raw)
            ),
            "musicbrainz_client": Mock(
                search_artist=Mock(return_value=self.mb_search),
                get_artist_details=Mock(return_value=self.mb_details),
            ),
            "save_raw_json": Mock(
                side_effect=["tadb-raw-key", "mb-search-key", "mb-raw-key"]
            ),
            "transform_theaudiodb_artist": Mock(return_value=self.tadb_normalized),
            "transform_musicbrainz_artist": Mock(return_value=self.mb_normalized),
            "enrich_artist": Mock(return_value=self.enriched),
            "save_processed_json": Mock(return_value="enriched-key"),
            "save_enriched_artist": Mock(),
        }

    def test_complete_flow_preserves_raw_serializes_and_returns_traceability(self):
        mocks = self._mocks()
        with patch.multiple(MODULE, **mocks):
            result = process_enriched_artist("Metallica")

        mocks["theaudiodb_client"].search_artist.assert_called_once_with("Metallica")
        mocks["musicbrainz_client"].search_artist.assert_called_once_with("Metallica")
        mocks["musicbrainz_client"].get_artist_details.assert_called_once_with("mbid-1")
        self.assertEqual(
            mocks["save_raw_json"].call_args_list,
            [
                call("theaudiodb", self.tadb_raw, "artists", "111279"),
                call("musicbrainz", self.mb_search, "artists", "mbid-1"),
                call("musicbrainz", self.mb_details, "artists", "mbid-1"),
            ],
        )
        self.assertIs(mocks["save_raw_json"].call_args_list[0].args[1], self.tadb_raw)
        self.assertIs(mocks["save_raw_json"].call_args_list[1].args[1], self.mb_search)
        self.assertIs(mocks["save_raw_json"].call_args_list[2].args[1], self.mb_details)
        mocks["transform_theaudiodb_artist"].assert_called_once_with(self.tadb_raw)
        mocks["transform_musicbrainz_artist"].assert_called_once_with(self.mb_details)
        mocks["enrich_artist"].assert_called_once_with(
            self.tadb_normalized, self.mb_normalized
        )
        mocks["save_processed_json"].assert_called_once_with(
            {
                "name": "Metallica",
                "country": "US",
                "genre": "Metal",
                "formed_year": None,
                "biography": None,
                "image_url": None,
                "source_ids": {"theaudiodb": "111279", "musicbrainz": "mbid-1"},
            },
            "artists",
            "111279",
            data_type="enriched",
        )
        mocks["save_enriched_artist"].assert_called_once_with(self.enriched)
        self.assertEqual(
            result,
            {
                "artist": self.enriched,
                "artist_name": "Metallica",
                "theaudiodb_artist_id": "111279",
                "musicbrainz_mbid": "mbid-1",
                "source": "theaudiodb+musicbrainz",
                "sources": {"theaudiodb": True, "musicbrainz": True},
                "theaudiodb_raw_s3_key": "tadb-raw-key",
                "musicbrainz_raw_s3_key": "mb-raw-key",
                "processed_s3_key": "enriched-key",
            },
        )

    def test_skips_results_without_a_usable_name_deterministically(self):
        mocks = self._mocks()
        mocks["musicbrainz_client"].search_artist.return_value = {
            "artists": [{"id": "ignored", "name": "  "}, {"id": "chosen", "name": "Metallica"}]
        }
        mocks["musicbrainz_client"].get_artist_details.return_value = {
            "id": "chosen", "name": "Metallica"
        }
        with patch.multiple(MODULE, **mocks):
            result = process_enriched_artist("Metallica")
        self.assertEqual(result["musicbrainz_mbid"], "chosen")

    def test_search_without_usable_result_returns_theaudiodb_partial(self):
        mocks = self._mocks()
        mocks["musicbrainz_client"].search_artist.return_value = {"artists": [None, {}]}
        with patch.multiple(MODULE, **mocks):
            result = process_enriched_artist("Metallica")
        self.assertEqual(result["source"], "theaudiodb")
        self.assertEqual(result["artist"].source_ids, {"theaudiodb": "111279"})

    def test_result_without_mbid_returns_theaudiodb_partial(self):
        mocks = self._mocks()
        mocks["musicbrainz_client"].search_artist.return_value = {"artists": [{"name": "Metallica"}]}
        with patch.multiple(MODULE, **mocks):
            result = process_enriched_artist("Metallica")
        self.assertEqual(result["sources"], {"theaudiodb": True, "musicbrainz": False})
        mocks["musicbrainz_client"].get_artist_details.assert_not_called()

    def test_each_failure_propagates_and_prevents_every_later_stage(self):
        stage_paths = [
            ("theaudiodb_client", "search_artist"),
            ("save_raw_json", None),
            ("transform_theaudiodb_artist", None),
            ("musicbrainz_client", "search_artist"),
            ("musicbrainz_client", "get_artist_details"),
            ("save_raw_json", None),
            ("transform_musicbrainz_artist", None),
            ("enrich_artist", None),
            ("save_processed_json", None),
            ("save_enriched_artist", None),
        ]
        for failed_index, (owner, method) in enumerate(stage_paths):
            with self.subTest(stage=failed_index):
                mocks = self._mocks()
                ordered = Mock()
                sequence = []
                for index, (stage_owner, stage_method) in enumerate(stage_paths):
                    target = mocks[stage_owner]
                    if stage_method:
                        target = getattr(target, stage_method)
                    # save_raw_json occurs twice; attach it only once.
                    if target not in sequence:
                        ordered.attach_mock(target, f"stage_{index}")
                        sequence.append(target)
                error = RuntimeError(f"failure-{failed_index}")
                if owner == "save_raw_json":
                    if failed_index == 1:
                        mocks[owner].side_effect = error
                    else:
                        mocks[owner].side_effect = ["tadb-raw-key", error]
                else:
                    target = mocks[owner]
                    if method:
                        target = getattr(target, method)
                    target.side_effect = error
                with patch.multiple(MODULE, **mocks), self.assertRaises(
                    RuntimeError
                ) as raised:
                    process_enriched_artist("Metallica")
                self.assertIs(raised.exception, error)
                if failed_index < 9:
                    self.assertNotIn(
                        "stage_9", [item[0] for item in ordered.mock_calls]
                    )

    def test_dynamodb_runs_only_after_processed_s3_succeeds(self):
        mocks = self._mocks()
        order = Mock()
        order.attach_mock(mocks["save_processed_json"], "s3")
        order.attach_mock(mocks["save_enriched_artist"], "dynamodb")

        with patch.multiple(MODULE, **mocks):
            process_enriched_artist("Metallica")

        self.assertEqual(
            [entry[0] for entry in order.mock_calls], ["s3", "dynamodb"]
        )

        mocks = self._mocks()
        failure = RuntimeError("S3 indisponível")
        mocks["save_processed_json"].side_effect = failure
        with patch.multiple(MODULE, **mocks), self.assertRaises(RuntimeError):
            process_enriched_artist("Metallica")
        mocks["save_enriched_artist"].assert_not_called()

    def test_dynamodb_failure_is_propagated(self):
        mocks = self._mocks()
        failure = RuntimeError("DynamoDB indisponível")
        mocks["save_enriched_artist"].side_effect = failure
        with patch.multiple(MODULE, **mocks), self.assertRaises(
            RuntimeError
        ) as raised:
            process_enriched_artist("Metallica")
        self.assertIs(raised.exception, failure)


if __name__ == "__main__":
    unittest.main()
