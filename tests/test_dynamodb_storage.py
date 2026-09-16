"""Testes unitários do storage DynamoDB, sem acesso à AWS."""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

from src.models import EnrichedArtist
from src.storage import DynamoDBStorageError, save_enriched_artist


class SaveEnrichedArtistTests(unittest.TestCase):
    def setUp(self):
        self.artist = EnrichedArtist(
            name="Björk",
            country="IS",
            genre=None,
            formed_year="1965",
            biography=None,
            image_url="https://example.test/bjork.jpg",
            source_ids={"theaudiodb": "112233", "musicbrainz": "mbid-1"},
        )
        self.table = Mock()
        self.resource = Mock()
        self.resource.Table.return_value = self.table
        self.environment = patch.dict(
            os.environ,
            {"SOUNDSCOPE_DYNAMODB_TABLE": "artists-test"},
            clear=False,
        )
        self.environment.start()

    def tearDown(self):
        self.environment.stop()

    def test_writes_expected_item_and_theaudiodb_partition_key(self):
        moment = datetime(2026, 9, 16, 15, 30, tzinfo=timezone.utc)

        result = save_enriched_artist(
            self.artist, dynamodb_resource=self.resource, updated_at=moment
        )

        self.assertIsNone(result)
        self.resource.Table.assert_called_once_with("artists-test")
        self.table.put_item.assert_called_once_with(
            Item={
                "artist-id": "112233",
                "name": "Björk",
                "country": "IS",
                "formed_year": "1965",
                "image_url": "https://example.test/bjork.jpg",
                "source_ids": {
                    "theaudiodb": "112233",
                    "musicbrainz": "mbid-1",
                },
                "members": [],
                "albums": [],
                "updated_at": "2026-09-16T15:30:00+00:00",
            }
        )

    def test_requires_table_environment_variable(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                DynamoDBStorageError, "SOUNDSCOPE_DYNAMODB_TABLE"
            ):
                save_enriched_artist(self.artist, dynamodb_resource=self.resource)
        self.resource.Table.assert_not_called()

    def test_wraps_boto3_error_and_keeps_original_cause(self):
        original = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
            "PutItem",
        )
        self.table.put_item.side_effect = original

        with self.assertRaises(DynamoDBStorageError) as raised:
            save_enriched_artist(self.artist, dynamodb_resource=self.resource)

        self.assertIs(raised.exception.__cause__, original)

    @patch("src.storage.dynamodb.boto3.resource")
    def test_uses_default_boto3_resource(self, boto_resource):
        boto_resource.return_value = self.resource
        save_enriched_artist(self.artist)
        boto_resource.assert_called_once_with("dynamodb")


if __name__ == "__main__":
    unittest.main()
