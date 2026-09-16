import unittest

from src.models import EnrichedAlbum, NormalizedAlbum
from src.pipeline.enrichment.artist import _merge_albums
from src.pipeline.transformers.musicbrainz import transform_musicbrainz_members
from src.pipeline.transformers.theaudiodb import transform_theaudiodb_artist


class ArtistProfileTests(unittest.TestCase):
    def _artist(self, **extra):
        artist = {"idArtist": "1", "strArtist": "Nome", **extra}
        return transform_theaudiodb_artist({"artists": [artist]})

    def test_biography_prefers_portuguese_then_english_and_allows_absence(self):
        self.assertEqual(
            self._artist(strBiographyPT=" PT ", strBiographyEN="EN").biography, "PT"
        )
        self.assertEqual(
            self._artist(strBiographyPT="", strBiographyEN=" EN ").biography, "EN"
        )
        self.assertIsNone(self._artist().biography)

    def test_album_merge_deduplicates_sorts_and_combines_ids(self):
        tadb = [NormalizedAlbum("theaudiodb", "a1", "1", "Alpha", "2000", "cover")]
        mb = [
            EnrichedAlbum("alpha", "2000", musicbrainz_release_group_id="rg1"),
            EnrichedAlbum("Beta", "1990"),
        ]
        result = _merge_albums(tadb, mb)
        self.assertEqual([item.title for item in result], ["Beta", "Alpha"])
        self.assertEqual(result[1].musicbrainz_release_group_id, "rg1")
        self.assertEqual(result[1].cover_url, "cover")

    def test_members_preserve_only_api_supplied_role_and_status(self):
        result = transform_musicbrainz_members(
            {
                "relations": [
                    {
                        "type": "member of band",
                        "artist": {"name": "Ana"},
                        "attributes": ["vocals"],
                        "ended": False,
                    },
                    {"type": "member of band", "artist": {"name": "Bia"}},
                ]
            }
        )
        self.assertEqual((result[0].role, result[0].active), ("vocals", True))
        self.assertEqual((result[1].role, result[1].active), (None, None))


if __name__ == "__main__":
    unittest.main()
