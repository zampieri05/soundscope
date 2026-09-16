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
        self.mock_sleep = self.sleep_patcher.start()
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


class RetryTests(MusicBrainzClientTestCase):
    @staticmethod
    def _response(
        status_code: int,
        data: dict[str, object] | None = None,
        retry_after: str | None = None,
    ) -> Mock:
        response = Mock()
        response.status_code = status_code
        response.headers = {"Retry-After": retry_after} if retry_after else {}
        if status_code >= 400:
            response.raise_for_status.side_effect = requests.HTTPError(
                f"{status_code} Server Error", response=response
            )
        response.json.return_value = data or {
            "artists": [{"id": "an-mbid", "name": "Metallica"}]
        }
        return response

    @patch("src.services.musicbrainz.client._wait_for_rate_limit")
    @patch("src.services.musicbrainz.client.requests.get")
    def test_success_on_first_attempt_does_not_sleep(
        self, mock_get: Mock, mock_rate_limit: Mock
    ) -> None:
        mock_get.return_value = self._response(200)

        search_artist("Metallica")

        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(mock_rate_limit.call_count, 1)
        self.mock_sleep.assert_not_called()

    @patch("src.services.musicbrainz.client._wait_for_rate_limit")
    @patch("src.services.musicbrainz.client.requests.get")
    def test_retries_503_then_succeeds(
        self, mock_get: Mock, mock_rate_limit: Mock
    ) -> None:
        mock_get.side_effect = [self._response(503), self._response(200)]

        search_artist("Metallica")

        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(mock_rate_limit.call_count, 2)
        self.mock_sleep.assert_called_once_with(1.0)

    @patch("src.services.musicbrainz.client._wait_for_rate_limit")
    @patch("src.services.musicbrainz.client.requests.get")
    def test_stops_after_three_503_responses_and_preserves_cause(
        self, mock_get: Mock, mock_rate_limit: Mock
    ) -> None:
        responses = [self._response(503) for _ in range(3)]
        mock_get.side_effect = responses

        with self.assertRaises(MusicBrainzError) as raised:
            get_artist_details("an-mbid")

        self.assertIsInstance(raised.exception.__cause__, requests.HTTPError)
        self.assertIs(raised.exception.__cause__.response, responses[-1])
        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_rate_limit.call_count, 3)
        self.assertEqual(
            self.mock_sleep.call_args_list,
            [unittest.mock.call(1.0), unittest.mock.call(2.0)],
        )

    @patch("src.services.musicbrainz.client._wait_for_rate_limit")
    @patch("src.services.musicbrainz.client.requests.get")
    def test_retries_429_then_succeeds(
        self, mock_get: Mock, _mock_rate_limit: Mock
    ) -> None:
        mock_get.side_effect = [self._response(429), self._response(200)]

        search_artist("Metallica")

        self.assertEqual(mock_get.call_count, 2)
        self.mock_sleep.assert_called_once_with(1.0)

    @patch("src.services.musicbrainz.client._wait_for_rate_limit")
    @patch("src.services.musicbrainz.client.requests.get")
    def test_uses_retry_after_when_present(
        self, mock_get: Mock, _mock_rate_limit: Mock
    ) -> None:
        mock_get.side_effect = [self._response(503, retry_after="7"), self._response(200)]

        search_artist("Metallica")

        self.assertEqual(mock_get.call_count, 2)
        self.mock_sleep.assert_called_once_with(7.0)

    @patch("src.services.musicbrainz.client._wait_for_rate_limit")
    @patch("src.services.musicbrainz.client.requests.get")
    def test_does_not_retry_404(
        self, mock_get: Mock, mock_rate_limit: Mock
    ) -> None:
        mock_get.return_value = self._response(404)

        with self.assertRaises(MusicBrainzError):
            get_artist_details("an-mbid")

        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(mock_rate_limit.call_count, 1)
        self.mock_sleep.assert_not_called()

    @patch("src.services.musicbrainz.client._wait_for_rate_limit")
    @patch("src.services.musicbrainz.client.requests.get")
    def test_connection_error_is_wrapped_without_retry(
        self, mock_get: Mock, mock_rate_limit: Mock
    ) -> None:
        connection_error = requests.ConnectionError("connection refused")
        mock_get.side_effect = connection_error

        with self.assertRaises(MusicBrainzError) as raised:
            search_artist("Metallica")

        self.assertIs(raised.exception.__cause__, connection_error)
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(mock_rate_limit.call_count, 1)
        self.mock_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
