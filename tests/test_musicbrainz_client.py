"""Testes unitários do cliente MusicBrainz, sem chamadas externas reais."""

import unittest
from unittest.mock import Mock, patch

import requests

from src.services.musicbrainz.client import (
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
    ArtistNotFoundError,
    MusicBrainzError,
    get_artist_details,
    search_artist,
)


class MusicBrainzClientTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.sleep_patcher = patch("src.services.musicbrainz.client.time.sleep")
        self.sleep_patcher.start()
        self.addCleanup(self.sleep_patcher.stop)


class SearchArtistTests(MusicBrainzClientTestCase):
    @patch.dict("os.environ", {}, clear=True)
    @patch("src.services.musicbrainz.client.requests.get")
    def test_returns_raw_json_and_builds_expected_request(self, mock_get: Mock) -> None:
        raw_data = {
            "created": "2026-01-01T00:00:00Z",
            "count": 1,
            "artists": [{"id": "65f4f0c5-ef9e-490c-aee3-909e7ae6b2ab", "name": "Metallica"}],
        }
        response = Mock()
        response.json.return_value = raw_data
        mock_get.return_value = response

        result = search_artist("  Metallica  ")

        self.assertIs(result, raw_data)
        mock_get.assert_called_once_with(
            "https://musicbrainz.org/ws/2/artist/",
            params={"query": "Metallica", "fmt": "json"},
            headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status.assert_called_once_with()

    def test_rejects_empty_artist_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "não pode estar vazio"):
            search_artist("   ")

    @patch("src.services.musicbrainz.client.requests.get")
    def test_handles_timeout(self, mock_get: Mock) -> None:
        mock_get.side_effect = requests.Timeout("timed out")
        with self.assertRaisesRegex(MusicBrainzError, "tempo limite"):
            search_artist("Metallica")

    @patch("src.services.musicbrainz.client.requests.get")
    def test_handles_http_error(self, mock_get: Mock) -> None:
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        mock_get.return_value = response
        with self.assertRaisesRegex(MusicBrainzError, "Erro HTTP"):
            search_artist("Metallica")

    @patch("src.services.musicbrainz.client.requests.get")
    def test_handles_invalid_json(self, mock_get: Mock) -> None:
        response = Mock()
        response.json.side_effect = ValueError("invalid JSON")
        mock_get.return_value = response
        with self.assertRaisesRegex(MusicBrainzError, "JSON inválida"):
            search_artist("Metallica")

    @patch("src.services.musicbrainz.client.requests.get")
    def test_handles_unexpected_structure(self, mock_get: Mock) -> None:
        response = Mock()
        response.json.return_value = {"results": []}
        mock_get.return_value = response
        with self.assertRaisesRegex(MusicBrainzError, "estrutura JSON inesperada"):
            search_artist("Metallica")

    @patch("src.services.musicbrainz.client.requests.get")
    def test_handles_artist_not_found(self, mock_get: Mock) -> None:
        response = Mock()
        response.json.return_value = {"count": 0, "artists": []}
        mock_get.return_value = response
        with self.assertRaisesRegex(ArtistNotFoundError, "não encontrado"):
            search_artist("Artista Inexistente")


class ArtistDetailsTests(MusicBrainzClientTestCase):
    @patch.dict(
        "os.environ", {"MUSICBRAINZ_USER_AGENT": "SoundScope-Test/1.0 (test@example.com)"}
    )
    @patch("src.services.musicbrainz.client.requests.get")
    def test_returns_raw_json_and_builds_expected_request(self, mock_get: Mock) -> None:
        mbid = "65f4f0c5-ef9e-490c-aee3-909e7ae6b2ab"
        raw_data = {
            "id": mbid,
            "name": "Metallica",
            "country": "US",
            "relations": [{"type": "member of band"}],
        }
        response = Mock()
        response.json.return_value = raw_data
        mock_get.return_value = response

        result = get_artist_details(f"  {mbid}  ")

        self.assertIs(result, raw_data)
        mock_get.assert_called_once_with(
            f"https://musicbrainz.org/ws/2/artist/{mbid}",
            params={"inc": "aliases+genres+tags+artist-rels", "fmt": "json"},
            headers={
                "User-Agent": "SoundScope-Test/1.0 (test@example.com)",
                "Accept": "application/json",
            },
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status.assert_called_once_with()

    def test_rejects_empty_mbid(self) -> None:
        with self.assertRaisesRegex(ValueError, "MBID"):
            get_artist_details("   ")

    @patch("src.services.musicbrainz.client.requests.get")
    def test_handles_timeout(self, mock_get: Mock) -> None:
        mock_get.side_effect = requests.Timeout("timed out")
        with self.assertRaisesRegex(MusicBrainzError, "tempo limite"):
            get_artist_details("an-mbid")

    @patch("src.services.musicbrainz.client.requests.get")
    def test_handles_http_error(self, mock_get: Mock) -> None:
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_get.return_value = response
        with self.assertRaisesRegex(MusicBrainzError, "Erro HTTP"):
            get_artist_details("an-mbid")

    @patch("src.services.musicbrainz.client.requests.get")
    def test_handles_invalid_json(self, mock_get: Mock) -> None:
        response = Mock()
        response.json.side_effect = ValueError("invalid JSON")
        mock_get.return_value = response
        with self.assertRaisesRegex(MusicBrainzError, "JSON inválida"):
            get_artist_details("an-mbid")

    @patch("src.services.musicbrainz.client.requests.get")
    def test_handles_unexpected_structure(self, mock_get: Mock) -> None:
        response = Mock()
        response.json.return_value = {"id": "an-mbid"}
        mock_get.return_value = response
        with self.assertRaisesRegex(MusicBrainzError, "estrutura JSON inesperada"):
            get_artist_details("an-mbid")


if __name__ == "__main__":
    unittest.main()
