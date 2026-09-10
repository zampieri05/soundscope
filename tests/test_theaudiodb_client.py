"""Testes unitários do cliente TheAudioDB, sem chamadas externas reais."""

import unittest
from unittest.mock import Mock, patch

import requests

from src.services.theaudiodb.client import (
    ArtistNotFoundError,
    DEFAULT_TIMEOUT_SECONDS,
    TheAudioDBError,
    search_artist,
)


class SearchArtistTests(unittest.TestCase):
    @patch.dict("os.environ", {"THEAUDIODB_API_KEY": "test-key"}, clear=True)
    @patch("src.services.theaudiodb.client.requests.get")
    def test_returns_raw_json_and_builds_expected_request(self, mock_get: Mock) -> None:
        raw_data = {"artists": [{"idArtist": "111", "strArtist": "Metallica"}]}
        response = Mock()
        response.json.return_value = raw_data
        mock_get.return_value = response

        result = search_artist("  Metallica  ")

        self.assertEqual(result, raw_data)
        mock_get.assert_called_once_with(
            "https://www.theaudiodb.com/api/v1/json/test-key/search.php",
            params={"s": "Metallica"},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status.assert_called_once_with()

    def test_rejects_empty_artist_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "não pode estar vazio"):
            search_artist("   ")

    @patch.dict("os.environ", {}, clear=True)
    def test_requires_api_key(self) -> None:
        with self.assertRaisesRegex(TheAudioDBError, "THEAUDIODB_API_KEY"):
            search_artist("Metallica")

    @patch.dict("os.environ", {"THEAUDIODB_API_KEY": "test-key"}, clear=True)
    @patch("src.services.theaudiodb.client.requests.get")
    def test_handles_timeout(self, mock_get: Mock) -> None:
        mock_get.side_effect = requests.Timeout("timed out")

        with self.assertRaisesRegex(TheAudioDBError, "tempo limite"):
            search_artist("Metallica")

    @patch.dict("os.environ", {"THEAUDIODB_API_KEY": "test-key"}, clear=True)
    @patch("src.services.theaudiodb.client.requests.get")
    def test_handles_http_error(self, mock_get: Mock) -> None:
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        mock_get.return_value = response

        with self.assertRaisesRegex(TheAudioDBError, "Erro HTTP"):
            search_artist("Metallica")

    @patch.dict("os.environ", {"THEAUDIODB_API_KEY": "test-key"}, clear=True)
    @patch("src.services.theaudiodb.client.requests.get")
    def test_handles_invalid_json(self, mock_get: Mock) -> None:
        response = Mock()
        response.json.side_effect = ValueError("invalid JSON")
        mock_get.return_value = response

        with self.assertRaisesRegex(TheAudioDBError, "JSON inválida"):
            search_artist("Metallica")

    @patch.dict("os.environ", {"THEAUDIODB_API_KEY": "test-key"}, clear=True)
    @patch("src.services.theaudiodb.client.requests.get")
    def test_handles_artist_not_found(self, mock_get: Mock) -> None:
        response = Mock()
        response.json.return_value = {"artists": None}
        mock_get.return_value = response

        with self.assertRaisesRegex(ArtistNotFoundError, "não encontrado"):
            search_artist("Artista Inexistente")


if __name__ == "__main__":
    unittest.main()
