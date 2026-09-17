"""Regressões da reconciliação conservadora TheAudioDB + MusicBrainz."""

import unittest
from unittest.mock import patch

from src.models import NormalizedArtist
from src.pipeline.processing.enriched import _same_identity, process_enriched_artist


MBID = "f59c5520-5f46-4d2c-b2c4-822eabf53419"
OTHER_MBID = "65f4f0c5-ef9e-490c-aee3-909e7ae6b2ab"


class IdentityRulesTests(unittest.TestCase):
    def _artists(self, *, tadb_mbid=None, tadb_country="California, USA",
                 tadb_code="US", mbid=MBID, mb_country="US"):
        tadb = NormalizedArtist(
            "theaudiodb", "ta", "Linkin Park", country=tadb_country,
            musicbrainz_id=tadb_mbid, country_code=tadb_code,
        )
        mb = NormalizedArtist(
            "musicbrainz", mbid, "Linkin Park", country=mb_country,
            musicbrainz_id=mbid, country_code=mb_country,
        )
        return tadb, mb

    def test_explicitly_different_valid_mbids_are_rejected(self):
        tadb, mb = self._artists(tadb_mbid=OTHER_MBID)
        with self.assertLogs("src.pipeline.processing.enriched", level="INFO") as logs:
            self.assertFalse(_same_identity(
                tadb, mb, {"name": "Linkin Park", "score": 100},
                {"id": MBID, "name": "Linkin Park", "country": "US"},
            ))
        self.assertIn("reason=mbid_mismatch", " ".join(logs.output))

    def test_without_mbid_incompatible_countries_are_rejected(self):
        tadb, mb = self._artists(
            tadb_mbid=None, tadb_country="Brazil", tadb_code=None,
            mbid="not-a-valid-mbid", mb_country="US",
        )
        self.assertFalse(_same_identity(
            tadb, mb, {"name": "Linkin Park", "score": 100},
            {"name": "Linkin Park", "country": "US"},
        ))

    def test_without_mbid_equivalent_country_variants_are_accepted(self):
        tadb, mb = self._artists(tadb_mbid=None, mbid="invalid")
        self.assertTrue(_same_identity(
            tadb, mb, {"name": "Linkin Park", "score": 100},
            {"name": "Linkin Park", "country": "US"},
        ))

    def test_low_score_remains_rejected(self):
        tadb, mb = self._artists(tadb_mbid=MBID)
        with self.assertLogs("src.pipeline.processing.enriched", level="INFO") as logs:
            self.assertFalse(_same_identity(
                tadb, mb, {"name": "Linkin Park", "score": 79},
                {"id": MBID, "name": "Linkin Park"},
            ))
        self.assertIn("reason=score_too_low", " ".join(logs.output))

    def test_valid_alias_still_matches(self):
        tadb, mb = self._artists(tadb_mbid=MBID)
        self.assertTrue(_same_identity(
            tadb, mb,
            {"name": "Canonical Name", "aliases": [{"name": "Linkin Park"}],
             "score": 100},
            {"id": MBID, "name": "Canonical Name"},
        ))


class LinkinParkPipelineRegressionTests(unittest.TestCase):
    def test_shared_mbid_preserves_theaudiodb_editorial_data_and_album(self):
        tadb_raw = {"artists": [{
            "idArtist": "111239", "strArtist": "Linkin Park",
            "strMusicBrainzID": MBID, "strCountry": "California, USA",
            "strCountryCode": "US", "strBiographyEN": "Biography",
            "strArtistThumb": "https://images.test/linkin-park.jpg",
        }]}
        albums_raw = {"album": [{
            "idAlbum": "123", "idArtist": "111239",
            "strAlbum": "Hybrid Theory", "intYearReleased": "2000",
            "strAlbumThumb": "https://images.test/hybrid-theory.jpg",
        }]}
        mb_search = {"artists": [{
            "id": MBID, "name": "Linkin Park", "country": "US", "score": 100,
        }]}
        mb_details = {"id": MBID, "name": "Linkin Park", "country": "US"}

        with patch("src.pipeline.processing.enriched.theaudiodb_client.search_artist",
                   return_value=tadb_raw), \
             patch("src.pipeline.processing.enriched.theaudiodb_client.search_albums",
                   return_value=albums_raw), \
             patch("src.pipeline.processing.enriched.musicbrainz_client.search_artist",
                   return_value=mb_search), \
             patch("src.pipeline.processing.enriched.musicbrainz_client.get_artist_details",
                   return_value=mb_details), \
             patch("src.pipeline.processing.enriched.musicbrainz_client.get_release_groups",
                   return_value={"release-groups": []}), \
             patch("src.pipeline.processing.enriched.save_raw_json", return_value="raw"), \
             patch("src.pipeline.processing.enriched.save_processed_json",
                   return_value="processed"), \
             patch("src.pipeline.processing.enriched.save_enriched_artist"):
            result = process_enriched_artist("Linkin Park")

        artist = result["artist"]
        self.assertEqual(result["sources"], {"theaudiodb": True, "musicbrainz": True})
        self.assertEqual(artist.biography, "Biography")
        self.assertEqual(artist.image_url, "https://images.test/linkin-park.jpg")
        self.assertEqual(len(artist.albums), 1)
        self.assertEqual(artist.albums[0].album_id, "123")
        self.assertEqual(
            artist.albums[0].cover_url, "https://images.test/hybrid-theory.jpg"
        )


if __name__ == "__main__":
    unittest.main()
