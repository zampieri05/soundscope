"""Testes do enriquecimento opcional do Cover Art Archive."""

import unittest
from unittest.mock import Mock, patch

import requests

from src.models import EnrichedAlbum
from src.pipeline.enrichment.covers import enrich_missing_covers
from src.services.coverartarchive import front_cover_url


class CoverArtClientTests(unittest.TestCase):
    @patch("src.services.coverartarchive.requests.get")
    def test_front_cover(self, get: Mock):
        get.return_value.status_code = 200
        get.return_value.json.return_value = {"images": [{"front": True, "thumbnails": {"500": "https://img/front.jpg"}}]}
        self.assertEqual(front_cover_url("rg-id"), "https://img/front.jpg")

    @patch("src.services.coverartarchive.requests.get")
    def test_404_timeout_and_transient_error_are_optional(self, get: Mock):
        get.return_value.status_code = 404
        self.assertIsNone(front_cover_url("missing"))
        for error in (requests.Timeout(), requests.ConnectionError()):
            get.side_effect = error
            self.assertIsNone(front_cover_url("unavailable"))


class CoverEnrichmentTests(unittest.TestCase):
    @patch("src.pipeline.enrichment.covers.front_cover_url", return_value="https://caa/front.jpg")
    def test_preserves_existing_cover_and_skips_release_without_mbid(self, lookup: Mock):
        albums = [
            EnrichedAlbum("TADB", cover_url="https://tadb/cover.jpg", musicbrainz_release_group_id="one"),
            EnrichedAlbum("CAA", musicbrainz_release_group_id="two"),
            EnrichedAlbum("No MBID"),
        ]
        result = enrich_missing_covers(albums)
        self.assertEqual(result[0].cover_url, "https://tadb/cover.jpg")
        self.assertEqual(result[1].cover_url, "https://caa/front.jpg")
        self.assertIsNone(result[2].cover_url)
        lookup.assert_called_once_with("two")

    @patch("src.pipeline.enrichment.covers.front_cover_url", side_effect=RuntimeError("transient"))
    def test_unexpected_caa_failure_never_drops_the_catalog(self, _lookup: Mock):
        albums = [EnrichedAlbum("Release", musicbrainz_release_group_id="one")]
        self.assertEqual(enrich_missing_covers(albums), albums)

    @patch("src.pipeline.enrichment.covers.front_cover_url", return_value=None)
    def test_lookup_budget_is_bounded(self, lookup: Mock):
        albums = [EnrichedAlbum(str(i), musicbrainz_release_group_id=str(i)) for i in range(30)]
        self.assertEqual(len(enrich_missing_covers(albums)), 30)
        self.assertEqual(lookup.call_count, 12)


if __name__ == "__main__":
    unittest.main()
