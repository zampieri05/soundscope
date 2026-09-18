"""Private, best-effort cache for Cover Art Archive release-group images."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
import logging
import os
import uuid
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
import requests

from src.models import EnrichedAlbum


logger = logging.getLogger(__name__)
MAX_CAA_LOOKUPS = 20
MAX_CAA_WORKERS = 5
CAA_TIMEOUT_SECONDS = 10


class CoverArtError(Exception):
    """A cover could not safely be obtained or cached."""


class CoverNotFoundError(CoverArtError):
    """The requested private cover is not present."""


def validate_release_group_id(value: Any) -> str:
    """Return a canonical MusicBrainz UUID, rejecting unsafe path values."""
    if not isinstance(value, str):
        raise ValueError("release_group_id must be a valid UUID")
    try:
        return str(uuid.UUID(value.strip()))
    except (ValueError, AttributeError) as exc:
        raise ValueError("release_group_id must be a valid UUID") from exc


def cover_key(release_group_id: str) -> str:
    return f"covers/release-groups/{validate_release_group_id(release_group_id)}.jpg"


def _bucket() -> str:
    bucket = os.getenv("SOUNDSCOPE_S3_BUCKET", "").strip()
    if not bucket:
        raise CoverArtError("SOUNDSCOPE_S3_BUCKET is not configured")
    return bucket


def _proxy_url(release_group_id: str) -> str:
    base_url = os.getenv("SOUNDSCOPE_API_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        raise CoverArtError("SOUNDSCOPE_API_BASE_URL is not configured")
    return f"{base_url}/cover/{release_group_id}"


def _is_missing(error: ClientError) -> bool:
    return str(error.response.get("Error", {}).get("Code", "")) in {
        "404", "NoSuchKey", "NotFound"
    }


def cache_cover(
    release_group_id: str,
    *,
    s3_client: Any | None = None,
    http_get: Any = requests.get,
) -> str:
    """Return the private proxy URL, downloading to S3 only on a cache miss."""
    release_group_id = validate_release_group_id(release_group_id)
    key, bucket = cover_key(release_group_id), _bucket()
    client = s3_client or boto3.client("s3")
    try:
        client.head_object(Bucket=bucket, Key=key)
        return _proxy_url(release_group_id)
    except ClientError as exc:
        if not _is_missing(exc):
            raise CoverArtError("failed to inspect private cover cache") from exc
    except BotoCoreError as exc:
        raise CoverArtError("failed to inspect private cover cache") from exc

    try:
        response = http_get(
            f"https://coverartarchive.org/release-group/{release_group_id}/front",
            timeout=CAA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        body = response.content
    except requests.RequestException as exc:
        raise CoverArtError("Cover Art Archive download failed") from exc
    if not content_type.startswith("image/") or not body:
        raise CoverArtError("Cover Art Archive response is not an image")
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
    except (BotoCoreError, ClientError) as exc:
        raise CoverArtError("failed to store cover in private cache") from exc
    return _proxy_url(release_group_id)


def get_cached_cover(
    release_group_id: str, *, s3_client: Any | None = None
) -> tuple[bytes, str]:
    """Read a private cover for the Lambda endpoint without exposing S3."""
    key, bucket = cover_key(release_group_id), _bucket()
    try:
        response = (s3_client or boto3.client("s3")).get_object(Bucket=bucket, Key=key)
        body = response["Body"].read()
        content_type = str(response.get("ContentType") or "image/jpeg")
        if not content_type.lower().startswith("image/"):
            raise CoverArtError("cached cover has an invalid content type")
        return body, content_type
    except ClientError as exc:
        if _is_missing(exc):
            raise CoverNotFoundError("cover not found") from exc
        raise CoverArtError("failed to read private cover cache") from exc
    except (BotoCoreError, KeyError, AttributeError, OSError) as exc:
        raise CoverArtError("failed to read private cover cache") from exc


def add_missing_covers(albums: list[EnrichedAlbum]) -> list[EnrichedAlbum]:
    """Fill only missing covers, concurrently and with a bounded CAA budget."""
    result = list(albums)
    # Spend the bounded CAA budget on the records users are most likely to
    # see first. MusicBrainz can return hundreds of release groups, including
    # singles, demos, live recordings and compilations before core albums.
    # Keep the final discography order untouched; this ranking is only for
    # choosing which missing covers to fetch.
    def cover_priority(item: tuple[int, EnrichedAlbum]) -> tuple[int, int, int]:
        index, album = item
        secondary = set(album.secondary_types or [])
        if album.primary_type == "Album" and not secondary:
            tier = 0
        elif album.primary_type == "Album":
            tier = 1
        elif album.primary_type == "EP":
            tier = 2
        elif album.primary_type == "Single":
            tier = 3
        else:
            tier = 4
        try:
            year = int(album.year or album.first_release_date[:4])
        except (TypeError, ValueError):
            year = 9999
        return tier, year, index

    missing = [
        (index, album)
        for index, album in enumerate(result)
        if not album.cover_url and album.musicbrainz_release_group_id
    ]
    candidates = [
        (index, album.musicbrainz_release_group_id)
        for index, album in sorted(missing, key=cover_priority)[:MAX_CAA_LOOKUPS]
    ]
    if not candidates:
        return result
    with ThreadPoolExecutor(max_workers=MAX_CAA_WORKERS) as executor:
        pending = {executor.submit(cache_cover, mbid): index for index, mbid in candidates}
        for future in as_completed(pending):
            try:
                result[pending[future]] = replace(
                    result[pending[future]], cover_url=future.result()
                )
            except Exception as exc:
                # Covers are optional enrichment. Never fail the artist pipeline.
                logger.warning("Cover enrichment failed error_type=%s", type(exc).__name__)
    return result

