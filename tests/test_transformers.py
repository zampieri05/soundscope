"""Testes unitários dos transformers, sem chamadas às APIs."""

import copy
import unittest

from src.models import NormalizedAlbum, NormalizedArtist
from src.pipeline.transformers import (
    transform_musicbrainz_artist,
    transform_theaudiodb_albums,
    transform_theaudiodb_artist,
)
from src.pipeline.transformers.errors import TransformationError


class TheAudioDBArtistTransformerTests(unittest.TestCase):
    def test_transforms_first_artist_and_preserves_source_and_id(self) -> None:
        raw = {
            "artists": [
                {
                    "idArtist": "111279",
                    "strArtist": " Metallica ",
                    "strCountry": "USA",
                    "strGenre": "Metal",
                    "intFormedYear": "1981",
                    "strBiographyEN": "A band biography.",
                    "strArtistThumb": "https://example.com/artist.jpg",
                },
                {"idArtist": "other", "strArtist": "Other"},
            ]
        }

        result = transform_theaudiodb_artist(raw)

        self.assertEqual(
            result,
            NormalizedArtist(
                source="theaudiodb",
                source_artist_id="111279",
                name="Metallica",
                country="USA",
                genre="Metal",
                formed_year="1981",
                biography="A band biography.",
                image_url="https://example.com/artist.jpg",
            ),
        )

    def test_optional_fields_are_none(self) -> None:
        result = transform_theaudiodb_artist(
            {"artists": [{"idArtist": "111", "strArtist": "Artist", "strGenre": " "}]}
        )
        self.assertIsNone(result.country)
        self.assertIsNone(result.genre)
        self.assertIsNone(result.biography)

    def test_rejects_invalid_structure(self) -> None:
        for raw in (None, {}, {"artists": None}, {"artists": []}, {"artists": ["bad"]}):
            with self.subTest(raw=raw), self.assertRaises(TransformationError):
                transform_theaudiodb_artist(raw)

    def test_rejects_missing_essential_fields(self) -> None:
        for artist in ({"strArtist": "Artist"}, {"idArtist": "111"}):
            with self.subTest(artist=artist), self.assertRaisesRegex(
                TransformationError, "obrigatório"
            ):
                transform_theaudiodb_artist({"artists": [artist]})

    def test_does_not_modify_raw_data(self) -> None:
        raw = {"artists": [{"idArtist": " 111 ", "strArtist": " Artist "}]}
        original = copy.deepcopy(raw)
        transform_theaudiodb_artist(raw)
        self.assertEqual(raw, original)


class MusicBrainzArtistTransformerTests(unittest.TestCase):
    def test_transforms_artist_and_preserves_source_and_mbid(self) -> None:
        raw = {
            "id": "65f4f0c5-ef9e-490c-aee3-909e7ae6b2ab",
            "name": " Metallica ",
            "country": "US",
            "genres": [{"name": "heavy metal"}, {"name": "thrash metal"}],
            "life-span": {"begin": "1981-10-28", "ended": False},
        }
        result = transform_musicbrainz_artist(raw)
        self.assertEqual(
            result,
            NormalizedArtist(
                source="musicbrainz",
                source_artist_id="65f4f0c5-ef9e-490c-aee3-909e7ae6b2ab",
                name="Metallica",
                country="US",
                genre="heavy metal",
                formed_year="1981",
            ),
        )

    def test_optional_fields_are_none(self) -> None:
        result = transform_musicbrainz_artist({"id": "mbid", "name": "Artist"})
        self.assertIsNone(result.country)
        self.assertIsNone(result.genre)
        self.assertIsNone(result.formed_year)
        self.assertIsNone(result.biography)
        self.assertIsNone(result.image_url)

    def test_rejects_invalid_structure(self) -> None:
        for raw in (None, [], "raw"):
            with self.subTest(raw=raw), self.assertRaises(TransformationError):
                transform_musicbrainz_artist(raw)

    def test_rejects_missing_essential_fields(self) -> None:
        for raw in ({"name": "Artist"}, {"id": "mbid"}, {"id": " ", "name": "Artist"}):
            with self.subTest(raw=raw), self.assertRaisesRegex(
                TransformationError, "obrigatório"
            ):
                transform_musicbrainz_artist(raw)

    def test_does_not_modify_raw_data(self) -> None:
        raw = {"id": " mbid ", "name": " Artist ", "genres": [{"name": " rock "}]}
        original = copy.deepcopy(raw)
        transform_musicbrainz_artist(raw)
        self.assertEqual(raw, original)


class TheAudioDBAlbumTransformerTests(unittest.TestCase):
    def test_transforms_album_list_and_preserves_ids(self) -> None:
        raw = {
            "album": [
                {
                    "idAlbum": "1",
                    "idArtist": "111",
                    "strAlbum": "Master of Puppets",
                    "intYearReleased": "1986",
                    "strAlbumThumb": "https://example.com/cover.jpg",
                }
            ]
        }
        self.assertEqual(
            transform_theaudiodb_albums(raw),
            [
                NormalizedAlbum(
                    source="theaudiodb",
                    source_album_id="1",
                    source_artist_id="111",
                    name="Master of Puppets",
                    release_year="1986",
                    cover_url="https://example.com/cover.jpg",
                )
            ],
        )

    def test_optional_fields_are_none(self) -> None:
        result = transform_theaudiodb_albums(
            {"album": [{"idAlbum": "1", "idArtist": "111", "strAlbum": "Album"}]}
        )
        self.assertIsNone(result[0].release_year)
        self.assertIsNone(result[0].cover_url)

    def test_null_and_empty_album_lists_are_empty(self) -> None:
        self.assertEqual(transform_theaudiodb_albums({"album": None}), [])
        self.assertEqual(transform_theaudiodb_albums({"album": []}), [])

    def test_does_not_modify_raw_data(self) -> None:
        raw = {"album": [{"idAlbum": " 1 ", "idArtist": " 111 ", "strAlbum": " Album "}]}
        original = copy.deepcopy(raw)
        transform_theaudiodb_albums(raw)
        self.assertEqual(raw, original)


if __name__ == "__main__":
    unittest.main()
