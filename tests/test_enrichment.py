"""Testes unitários do enriquecimento, sem acesso às APIs."""

import unittest

from src.models import EnrichedArtist, NormalizedArtist
from src.pipeline.enrichment import ArtistEnrichmentError, enrich_artist


def artist(source: str, source_id: str, **values: str | None) -> NormalizedArtist:
    return NormalizedArtist(
        source=source,
        source_artist_id=source_id,
        name=values.pop("name", "Metallica") or "",
        **values,
    )


class ArtistEnrichmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tadb = artist(
            "theaudiodb",
            "111279",
            country="USA",
            genre="Metal",
            formed_year="1982",
            biography="A band biography.",
            image_url="https://example.com/metallica.jpg",
        )
        self.mb = artist(
            "musicbrainz",
            "65f4f0c5-ef9e-490c-aee3-909e7ae6b2ab",
            country="US",
            genre="heavy metal",
            formed_year="1981",
        )

    def test_enriches_equivalent_artists_with_documented_priorities(self) -> None:
        result = enrich_artist(self.tadb, self.mb)

        self.assertEqual(
            result,
            EnrichedArtist(
                name="Metallica",
                country="US",
                genre="Metal",
                formed_year="1981",
                biography="A band biography.",
                image_url="https://example.com/metallica.jpg",
                source_ids={
                    "theaudiodb": "111279",
                    "musicbrainz": "65f4f0c5-ef9e-490c-aee3-909e7ae6b2ab",
                },
            ),
        )

    def test_name_comparison_is_case_insensitive(self) -> None:
        result = enrich_artist(self.tadb, artist("musicbrainz", "mbid", name="METALLICA"))
        self.assertEqual(result.name, "Metallica")

    def test_name_comparison_ignores_extra_spaces(self) -> None:
        spaced = artist("musicbrainz", "mbid", name="  Metallica   ")
        self.assertEqual(enrich_artist(self.tadb, spaced).name, "Metallica")

    def test_rejects_different_names(self) -> None:
        with self.assertRaisesRegex(ArtistEnrichmentError, "nomes diferentes"):
            enrich_artist(self.tadb, artist("musicbrainz", "mbid", name="Megadeth"))

    def test_country_prefers_musicbrainz_and_falls_back_to_theaudiodb(self) -> None:
        self.assertEqual(enrich_artist(self.tadb, self.mb).country, "US")
        self.assertEqual(
            enrich_artist(self.tadb, artist("musicbrainz", "mbid")).country, "USA"
        )

    def test_formed_year_prefers_musicbrainz_and_falls_back_to_theaudiodb(self) -> None:
        self.assertEqual(enrich_artist(self.tadb, self.mb).formed_year, "1981")
        self.assertEqual(
            enrich_artist(self.tadb, artist("musicbrainz", "mbid")).formed_year,
            "1982",
        )

    def test_biography_and_image_prefer_theaudiodb(self) -> None:
        mb = artist(
            "musicbrainz",
            "mbid",
            biography="MusicBrainz biography",
            image_url="https://example.com/mb.jpg",
        )
        result = enrich_artist(self.tadb, mb)
        self.assertEqual(result.biography, "A band biography.")
        self.assertEqual(result.image_url, "https://example.com/metallica.jpg")

    def test_genre_prefers_theaudiodb_and_falls_back_to_musicbrainz(self) -> None:
        self.assertEqual(enrich_artist(self.tadb, self.mb).genre, "Metal")
        tadb_without_genre = artist("theaudiodb", "111", genre=None)
        self.assertEqual(enrich_artist(tadb_without_genre, self.mb).genre, "heavy metal")

    def test_fields_missing_from_both_sources_are_none(self) -> None:
        result = enrich_artist(
            artist("theaudiodb", "111"), artist("musicbrainz", "mbid")
        )
        self.assertIsNone(result.country)
        self.assertIsNone(result.genre)
        self.assertIsNone(result.formed_year)
        self.assertIsNone(result.biography)
        self.assertIsNone(result.image_url)

    def test_preserves_both_source_ids(self) -> None:
        self.assertEqual(
            enrich_artist(self.tadb, self.mb).source_ids,
            {"theaudiodb": "111279", "musicbrainz": self.mb.source_artist_id},
        )

    def test_does_not_modify_normalized_inputs(self) -> None:
        original_tadb = self.tadb
        original_mb = self.mb
        enrich_artist(self.tadb, self.mb)
        self.assertEqual(self.tadb, original_tadb)
        self.assertEqual(self.mb, original_mb)

    def test_rejects_sources_in_the_wrong_arguments(self) -> None:
        with self.assertRaisesRegex(ArtistEnrichmentError, "theaudiodb_artist"):
            enrich_artist(self.mb, self.mb)
        with self.assertRaisesRegex(ArtistEnrichmentError, "musicbrainz_artist"):
            enrich_artist(self.tadb, self.tadb)


if __name__ == "__main__":
    unittest.main()
