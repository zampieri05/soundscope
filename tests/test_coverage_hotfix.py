"""Regression tests for resilient search and complete MusicBrainz catalog."""
import unittest
from unittest.mock import patch, call

from src.models import EnrichedAlbum, NormalizedAlbum
from src.pipeline.enrichment.artist import _merge_albums
from src.pipeline.processing.enriched import _select_musicbrainz_artist
from src.pipeline.transformers.musicbrainz import transform_musicbrainz_albums
from src.services.musicbrainz.client import ArtistNotFoundError, get_release_groups


class CandidateSelectionTests(unittest.TestCase):
    def test_later_exact_candidate_wins_and_preserves_official_score(self):
        raw = {"artists": [
            {"id": "wrong", "name": "Someone Else", "score": 100},
            {"id": "right", "name": "Beyoncé", "score": 96, "type": "Person"},
        ]}
        self.assertEqual(_select_musicbrainz_artist(raw, "beyonce")["id"], "right")
        self.assertEqual(raw["artists"][1]["score"], 96)

    def test_alias_case_and_diacritics_are_exact_after_normalization(self):
        raw = {"artists": [{"id": "1", "name": "Canonical", "score": 90,
                            "aliases": [{"name": "BÉYONCÉ"}]}]}
        self.assertEqual(_select_musicbrainz_artist(raw, "beyoncé")["id"], "1")

    def test_low_confidence_and_indistinguishable_homonyms_are_rejected(self):
        with self.assertRaises(ArtistNotFoundError):
            _select_musicbrainz_artist({"artists": [{"id": "1", "name": "X", "score": 79}]}, "X")
        with self.assertRaises(ArtistNotFoundError):
            _select_musicbrainz_artist({"artists": [
                {"id": "1", "name": "X", "score": 100},
                {"id": "2", "name": "X", "score": 100},
            ]}, "X")


class ReleaseGroupPaginationTests(unittest.TestCase):
    @patch("src.services.musicbrainz.client._get_json")
    def test_zero_and_one_item(self, request):
        request.return_value = {"release-group-count": 0, "release-groups": []}
        self.assertEqual(get_release_groups("id")["release-groups"], [])
        request.return_value = {"release-group-count": 1, "release-groups": [{"id": "1"}]}
        self.assertEqual(len(get_release_groups("id")["release-groups"]), 1)

    @patch("src.services.musicbrainz.client._get_json")
    def test_101_items_use_offsets_and_deduplicate(self, request):
        first = [{"id": str(i)} for i in range(100)]
        request.side_effect = [
            {"release-group-count": 101, "release-groups": first},
            {"release-group-count": 101, "release-groups": [{"id": "99"}, {"id": "100"}]},
        ]
        result = get_release_groups("artist")
        self.assertEqual(len(result["release-groups"]), 101)
        self.assertEqual([c.kwargs["params"]["offset"] for c in request.call_args_list], ["0", "100"])

    @patch("src.services.musicbrainz.client._get_json")
    def test_empty_intermediate_page_stops_inconsistent_count(self, request):
        request.side_effect = [
            {"release-group-count": 200, "release-groups": [{"id": str(i)} for i in range(100)]},
            {"release-group-count": 200, "release-groups": []},
        ]
        result = get_release_groups("artist")
        self.assertEqual(len(result["release-groups"]), 100)
        self.assertEqual(request.call_count, 2)


class CompleteDiscographyTests(unittest.TestCase):
    def test_sizes_are_not_domain_capped(self):
        for size in (20, 21, 99, 100, 101, 200):
            with self.subTest(size=size):
                albums = [EnrichedAlbum(str(i), "2020", musicbrainz_release_group_id=str(i)) for i in range(size)]
                self.assertEqual(len(_merge_albums([], albums)), size)

    def test_types_dates_and_missing_cover_are_preserved(self):
        raw = {"release-groups": [
            {"id": "a", "title": "A", "primary-type": "Album", "secondary-types": ["Live"], "first-release-date": "2020-01-02"},
            {"id": "e", "title": "E", "primary-type": "EP", "secondary-types": ["Compilation"]},
            {"id": "s", "title": "S", "primary-type": "Single"},
            {"id": "b", "title": "B", "primary-type": "Broadcast"},
        ]}
        result = transform_musicbrainz_albums(raw)
        self.assertEqual([item.primary_type for item in result], ["Album", "EP", "Single", "Broadcast"])
        self.assertEqual(result[0].secondary_types, ["Live"])
        self.assertEqual(result[0].first_release_date, "2020-01-02")
        self.assertTrue(all(item.cover_url is None for item in result))
        self.assertIsNone(result[1].year)

    def test_distinct_ids_and_editorial_titles_are_not_merged(self):
        albums = [
            EnrichedAlbum("Album", "2020", musicbrainz_release_group_id="1"),
            EnrichedAlbum("Album", "2020", musicbrainz_release_group_id="2"),
            EnrichedAlbum("Album (Deluxe Edition)", "2020", musicbrainz_release_group_id="3"),
            EnrichedAlbum("Álbum (Remastered)", None, musicbrainz_release_group_id="4"),
        ]
        self.assertEqual(len(_merge_albums([], albums)), 4)

class ResilientPipelineTests(unittest.TestCase):
    def _run(self, tadb_effect, mb_effect):
        from src.pipeline.processing.enriched import process_enriched_artist
        tadb_raw = {"artists": [{"idArtist": "ta", "strArtist": "Beyoncé"}]}
        mb_search = {"artists": [{"id": "mb", "name": "Beyoncé", "score": 100, "type": "Person"}]}
        with patch("src.pipeline.processing.enriched.theaudiodb_client.search_artist", side_effect=tadb_effect or [tadb_raw]), \
             patch("src.pipeline.processing.enriched.theaudiodb_client.search_albums", side_effect=__import__('src.services.theaudiodb.client', fromlist=['AlbumsNotFoundError']).AlbumsNotFoundError("none")), \
             patch("src.pipeline.processing.enriched.musicbrainz_client.search_artist", side_effect=mb_effect or [mb_search]), \
             patch("src.pipeline.processing.enriched.musicbrainz_client.get_artist_details", return_value={"id": "mb", "name": "Beyoncé"}), \
             patch("src.pipeline.processing.enriched.musicbrainz_client.get_release_groups", return_value={"release-groups": []}), \
             patch("src.pipeline.processing.enriched.save_raw_json", return_value="raw"), \
             patch("src.pipeline.processing.enriched.save_processed_json", return_value="processed"), \
             patch("src.pipeline.processing.enriched.save_enriched_artist") as dynamo:
            return process_enriched_artist("Beyonce"), dynamo

    def test_both_sources_contribute(self):
        result, dynamo = self._run(None, None)
        self.assertEqual(result["sources"], {"theaudiodb": True, "musicbrainz": True})
        dynamo.assert_called_once()

    def test_theaudiodb_empty_or_temporarily_down_uses_musicbrainz(self):
        from src.services.theaudiodb.client import ArtistNotFoundError, TheAudioDBError
        for error in (ArtistNotFoundError("none"), TheAudioDBError("down")):
            with self.subTest(error=type(error).__name__):
                result, dynamo = self._run([error], None)
                self.assertEqual(result["artist"].source_ids, {"musicbrainz": "mb"})
                self.assertEqual(result["sources"], {"theaudiodb": False, "musicbrainz": True})
                dynamo.assert_not_called()

    def test_musicbrainz_empty_or_temporarily_down_uses_theaudiodb(self):
        from src.services.musicbrainz.client import ArtistNotFoundError, MusicBrainzError
        for error in (ArtistNotFoundError("none"), MusicBrainzError("down")):
            with self.subTest(error=type(error).__name__):
                result, dynamo = self._run(None, [error])
                self.assertEqual(result["artist"].source_ids, {"theaudiodb": "ta"})
                self.assertEqual(result["sources"], {"theaudiodb": True, "musicbrainz": False})
                dynamo.assert_called_once()

    def test_neither_source_found_is_not_found(self):
        from src.services.theaudiodb.client import ArtistNotFoundError as TNotFound
        from src.services.musicbrainz.client import ArtistNotFoundError as MNotFound
        from src.pipeline.ingestion.errors import UsableArtistNotFoundError
        with self.assertRaises(UsableArtistNotFoundError):
            self._run([TNotFound("none")], [MNotFound("none")])

    def test_country_conflict_never_builds_hybrid(self):
        from src.pipeline.processing.enriched import _same_identity
        from src.models import NormalizedArtist
        ta = NormalizedArtist("theaudiodb", "ta", "Same", country="BR")
        mb = NormalizedArtist("musicbrainz", "mb", "Same", country="US")
        self.assertFalse(_same_identity(ta, mb, {"name": "Same", "score": 100}, {"name": "Same"}))
