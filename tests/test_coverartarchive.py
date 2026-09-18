"""Tests for the private Cover Art Archive cache and cover endpoint."""

import base64
import json
import os
import unittest
import uuid
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

from src.handlers.artist import lambda_handler
from src.models import EnrichedAlbum
from src.services.coverartarchive import (
    CoverArtError,
    add_missing_covers,
    cache_cover,
)


MBID = "12345678-1234-4234-8234-123456789abc"
KEY = f"covers/release-groups/{MBID}.jpg"


def missing() -> ClientError:
    return ClientError({"Error": {"Code": "404", "Message": "missing"}}, "HeadObject")


class CoverCacheTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "SOUNDSCOPE_S3_BUCKET": "private-bucket",
            "SOUNDSCOPE_API_BASE_URL": "https://api.example.test",
        })
        self.environment.start()
        self.s3 = Mock()

    def tearDown(self):
        self.environment.stop()

    def test_cache_hit_does_not_download_or_write(self):
        get = Mock()
        url = cache_cover(MBID, s3_client=self.s3, http_get=get)
        self.assertEqual(url, f"https://api.example.test/cover/{MBID}")
        self.s3.head_object.assert_called_once_with(Bucket="private-bucket", Key=KEY)
        get.assert_not_called()
        self.s3.put_object.assert_not_called()

    def test_cache_miss_downloads_image_and_puts_private_object(self):
        self.s3.head_object.side_effect = missing()
        response = Mock(content=b"jpeg bytes", headers={"Content-Type": "image/jpeg; charset=binary"})
        get = Mock(return_value=response)

        cache_cover(MBID, s3_client=self.s3, http_get=get)

        response.raise_for_status.assert_called_once_with()
        self.s3.put_object.assert_called_once_with(
            Bucket="private-bucket", Key=KEY, Body=b"jpeg bytes", ContentType="image/jpeg"
        )
        self.assertNotIn("ACL", self.s3.put_object.call_args.kwargs)

    def test_rejects_non_image_response(self):
        self.s3.head_object.side_effect = missing()
        response = Mock(content=b"html", headers={"Content-Type": "text/html"})
        with self.assertRaisesRegex(CoverArtError, "not an image"):
            cache_cover(MBID, s3_client=self.s3, http_get=Mock(return_value=response))
        self.s3.put_object.assert_not_called()

    @patch("src.services.coverartarchive.cache_cover", side_effect=CoverArtError("offline"))
    def test_external_failure_does_not_fail_album_pipeline(self, _cache):
        album = EnrichedAlbum("Album", musicbrainz_release_group_id=MBID)
        self.assertEqual(add_missing_covers([album]), [album])

    @patch("src.services.coverartarchive.cache_cover")
    def test_core_albums_are_prioritized_within_cover_budget(self, cache):
        cache.side_effect = lambda mbid: f"https://api.example.test/cover/{mbid}"
        items = [
            EnrichedAlbum(
                f"Single {index}",
                year="2000",
                musicbrainz_release_group_id=str(uuid.UUID(int=index + 1)),
                primary_type="Single",
            )
            for index in range(20)
        ]
        core_mbid = str(uuid.UUID(int=100))
        items.append(EnrichedAlbum(
            "Core Album",
            year="2001",
            musicbrainz_release_group_id=core_mbid,
            primary_type="Album",
        ))

        enriched = add_missing_covers(items)

        self.assertEqual(cache.call_count, 20)
        self.assertEqual(enriched[-1].cover_url, f"https://api.example.test/cover/{core_mbid}")

    @patch("src.services.coverartarchive.cache_cover")
    def test_existing_theaudiodb_cover_is_never_replaced(self, cache):
        album = EnrichedAlbum(
            "Album", musicbrainz_release_group_id=MBID,
            cover_url="https://theaudiodb.example.test/cover.jpg",
        )
        self.assertEqual(add_missing_covers([album]), [album])
        cache.assert_not_called()


class CoverEndpointTests(unittest.TestCase):
    @patch("src.handlers.artist.get_cached_cover", return_value=(b"image", "image/png"))
    def test_returns_base64_image_with_content_type(self, get_cover):
        response = lambda_handler({"pathParameters": {"release_group_id": MBID}}, None)
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(response["headers"]["Content-Type"], "image/png")
        self.assertTrue(response["isBase64Encoded"])
        self.assertEqual(base64.b64decode(response["body"]), b"image")
        get_cover.assert_called_once_with(MBID)

    @patch("src.handlers.artist.get_cached_cover")
    def test_invalid_mbid_returns_400_without_s3_read(self, get_cover):
        response = lambda_handler({"pathParameters": {"release_group_id": "../bad"}}, None)
        self.assertEqual(response["statusCode"], 400)
        self.assertEqual(json.loads(response["body"]), {"error": "invalid release_group_id"})
        get_cover.assert_not_called()

    @patch("src.services.coverartarchive.boto3.client")
    def test_missing_cover_returns_404(self, boto_client):
        boto_client.return_value.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject"
        )
        with patch.dict(os.environ, {"SOUNDSCOPE_S3_BUCKET": "private-bucket"}):
            response = lambda_handler({"pathParameters": {"release_group_id": MBID}}, None)
        self.assertEqual(response["statusCode"], 404)
        self.assertEqual(json.loads(response["body"]), {"error": "cover not found"})


if __name__ == "__main__":
    unittest.main()
