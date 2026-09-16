"""Unit tests for the API Gateway-compatible artist Lambda handler."""

import json
import unittest
from unittest.mock import patch

from src.handlers.artist import lambda_handler
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
        pipeline.return_value = {"artist_name": "Metallica", "processed_s3_key": "key"}

        response = lambda_handler(
            {"pathParameters": {"artist_name": "  Metallica  "}}, None
        )

        self.assertEqual(
            self.assert_proxy_response(response, 200), pipeline.return_value
        )
        pipeline.assert_called_once_with("Metallica")

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
        response = lambda_handler(
            {"pathParameters": {"artist_name": "Unknown"}}, None
        )
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
