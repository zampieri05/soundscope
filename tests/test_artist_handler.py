"""Unit tests for the API Gateway-compatible artist Lambda handler."""

from dataclasses import dataclass
import json
import unittest
from unittest.mock import patch

from src.handlers.artist import lambda_handler
from src.models import EnrichedArtist
from src.services.theaudiodb.client import ArtistNotFoundError

PIPELINE = "src.handlers.artist.process_enriched_artist"


class ArtistLambdaHandlerTests(unittest.TestCase):
    def assert_proxy_response(self, response, status):
        self.assertEqual(response["statusCode"], status)
        self.assertEqual(response["headers"]["Content-Type"], "application/json")
        self.assertEqual(response["headers"]["Access-Control-Allow-Origin"], "*")
        return json.loads(response["body"])

    @patch(PIPELINE)
    def test_valid_artist_returns_200_and_calls_pipeline(self, pipeline):
        enriched = EnrichedArtist(
            name="Metallica",
            country="US",
            genre="Metal",
            formed_year="1981",
            biography=None,
            image_url="https://example.com/metallica.jpg",
            source_ids={"theaudiodb": "111279", "musicbrainz": "mbid-1"},
        )
        pipeline.return_value = {
            "artist": enriched,
            "artist_name": "Metallica",
            "theaudiodb_artist_id": "111279",
            "musicbrainz_mbid": "mbid-1",
            "source": "theaudiodb+musicbrainz",
            "theaudiodb_raw_s3_key": "raw/tadb.json",
            "musicbrainz_raw_s3_key": "raw/mb.json",
            "processed_s3_key": "processed/enriched.json",
        }

        response = lambda_handler(
            {"pathParameters": {"artist_name": "  Metallica  "}}, None
        )

        self.assertEqual(
            self.assert_proxy_response(response, 200),
            {
                "artist": {
                    "name": "Metallica",
                    "country": "US",
                    "genre": "Metal",
                    "formed_year": "1981",
                    "biography": None,
                    "image_url": "https://example.com/metallica.jpg",
                    "source_ids": {
                        "theaudiodb": "111279",
                        "musicbrainz": "mbid-1",
                    },
                    "members": [],
                    "albums": [],
                },
                "metadata": {
                    "artist_name": "Metallica",
                    "theaudiodb_artist_id": "111279",
                    "musicbrainz_mbid": "mbid-1",
                    "source": "theaudiodb+musicbrainz",
                    "theaudiodb_raw_s3_key": "raw/tadb.json",
                    "musicbrainz_raw_s3_key": "raw/mb.json",
                    "processed_s3_key": "processed/enriched.json",
                },
            },
        )
        pipeline.assert_called_once_with("Metallica")

    @patch(PIPELINE)
    def test_serializes_nested_dataclasses_lists_and_optional_values(self, pipeline):
        @dataclass
        class NestedValue:
            labels: list[str]
            optional: str | None = None

        pipeline.return_value = {
            "artist": NestedValue(labels=["one", "two"]),
            "artist_name": "Example",
        }

        response = lambda_handler({"pathParameters": {"artist_name": "Example"}}, None)

        self.assertEqual(
            self.assert_proxy_response(response, 200),
            {
                "artist": {"labels": ["one", "two"], "optional": None},
                "metadata": {"artist_name": "Example"},
            },
        )

    @patch(PIPELINE)
    def test_missing_path_parameters_returns_400(self, pipeline):
        body = self.assert_proxy_response(lambda_handler({}, None), 400)
        self.assertEqual(body, {"error": "artist_name is required"})
        pipeline.assert_not_called()

    @patch(PIPELINE)
    def test_missing_artist_name_returns_400(self, pipeline):
        response = lambda_handler({"pathParameters": {}}, None)
        self.assertEqual(
            self.assert_proxy_response(response, 400),
            {"error": "artist_name is required"},
        )
        pipeline.assert_not_called()

    @patch(PIPELINE)
    def test_empty_artist_name_returns_400(self, pipeline):
        response = lambda_handler({"pathParameters": {"artist_name": " \t"}}, None)
        self.assertEqual(
            self.assert_proxy_response(response, 400),
            {"error": "artist_name is required"},
        )
        pipeline.assert_not_called()

    @patch(PIPELINE, side_effect=ArtistNotFoundError("sensitive upstream message"))
    def test_artist_not_found_returns_safe_404(self, pipeline):
        response = lambda_handler({"pathParameters": {"artist_name": "Unknown"}}, None)
        self.assertEqual(
            self.assert_proxy_response(response, 404), {"error": "artist not found"}
        )
        pipeline.assert_called_once_with("Unknown")

    @patch(PIPELINE, side_effect=RuntimeError("secret AWS detail"))
    def test_unexpected_error_returns_safe_500(self, pipeline):
        response = lambda_handler(
            {"pathParameters": {"artist_name": "Metallica"}}, None
        )
        body = self.assert_proxy_response(response, 500)
        self.assertEqual(body, {"error": "internal server error"})
        self.assertNotIn("secret", response["body"])


if __name__ == "__main__":
    unittest.main()
