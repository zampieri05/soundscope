"""Tests for the processed-result cache without network or AWS access."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import io
import json
import logging
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
import pytest

from src.cache.artist import (
    ArtistCacheError,
    ArtistCacheMiss,
    ArtistCacheStale,
    load_cached_artist,
    normalize_artist_search,
    save_artist_cache_index,
)
from src.handlers import artist as handler
from src.models import ArtistMember, EnrichedAlbum, EnrichedArtist
from src.storage.s3 import S3ObjectNotFoundError, S3StorageError, get_json
from src.utils.telemetry import InvocationMetrics, activate, deactivate


NOW = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)
PROCESSED_KEY = "processed/enriched/artists/111279/20260917T120000000000Z.json"


def _artist():
    return EnrichedArtist(
        name="Linkin Park", country="US", genre="Alternative Rock",
        formed_year="1996", biography="Biography", image_url="https://image",
        source_ids={"theaudiodb": "111279", "musicbrainz": "mbid-1"},
        members=[ArtistMember("Mike Shinoda", "vocals", True)],
        albums=[EnrichedAlbum(
            title="Hybrid Theory", year="2000", album_id="album-1",
            musicbrainz_release_group_id="rg-1", cover_url="https://cover",
            primary_type="Album", secondary_types=["Studio"],
            first_release_date="2000-10-24")],
    )


def _result():
    return {
        "artist": _artist(), "artist_name": "Linkin Park",
        "theaudiodb_artist_id": "111279", "musicbrainz_mbid": "mbid-1",
        "source": "theaudiodb+musicbrainz",
        "sources": {"theaudiodb": True, "musicbrainz": True},
        "theaudiodb_raw_s3_key": "raw/theaudiodb/artists/111279/a.json",
        "musicbrainz_raw_s3_key": "raw/musicbrainz/artists/mbid-1/b.json",
        "processed_s3_key": PROCESSED_KEY,
    }


def _documents(cached_at=NOW):
    captured = {}
    save_artist_cache_index(
        "Linkin Park", _result(), now=cached_at,
        put=lambda key, value: captured.update(key=key, index=value),
    )
    return captured["key"], captured["index"], asdict(_artist())


def _cache_get(index, processed):
    def get(key):
        return index if key.startswith("cache/") else processed
    return get


def _records(caplog):
    return [json.loads(record.message) for record in caplog.records
            if record.message.startswith('{"event":"artist_pipeline_completed"')]


def test_normalization_is_conservative_deterministic_and_not_fuzzy():
    assert normalize_artist_search("Linkin Park") == "linkin park"
    assert normalize_artist_search(" LINKIN   PARK ") == "linkin park"
    assert normalize_artist_search("Linkin Park Tribute") != "linkin park"
    first_key, _, _ = _documents()
    captured = {}
    save_artist_cache_index(
        "  LINKIN   PARK ", _result(), now=NOW,
        put=lambda key, value: captured.update(key=key),
    )
    assert captured["key"] == first_key
    assert "linkin" not in first_key


def test_index_is_minimal_safe_and_contains_no_artist_payload_or_secret():
    _, index, _ = _documents()
    assert set(index) == {"version", "processed_s3_key", "cached_at", "metadata"}
    serialized = json.dumps(index)
    assert "Biography" not in serialized
    assert "https://image" not in serialized
    assert "token" not in serialized.casefold()
    assert "api_key" not in serialized.casefold()


def test_valid_cache_hit_restores_complete_domain_result_and_age():
    _, index, processed = _documents(NOW - timedelta(hours=1))
    result, age = load_cached_artist(
        "linkin park", now=NOW, get=_cache_get(index, processed))
    assert result == _result()
    assert age == 3600
    assert result["artist"].members[0].name == "Mike Shinoda"
    assert result["artist"].albums[0].secondary_types == ["Studio"]


def test_valid_hit_measures_index_lookup_and_processed_read():
    _, index, processed = _documents()
    metrics = InvocationMetrics()
    token = activate(metrics)
    try:
        load_cached_artist(
            "Linkin Park", now=NOW, get=_cache_get(index, processed))
    finally:
        deactivate(token)
    assert metrics.values["cache.lookup_ms"] >= 0
    assert metrics.values["cache.processed_read_ms"] >= 0


def test_missing_index_is_a_miss():
    def missing(_key):
        raise S3ObjectNotFoundError("missing")
    with pytest.raises(ArtistCacheMiss):
        load_cached_artist("Linkin Park", now=NOW, get=missing)


def test_expired_index_is_stale_and_does_not_read_processed(monkeypatch):
    _, index, processed = _documents(NOW - timedelta(hours=25))
    get = Mock(side_effect=_cache_get(index, processed))
    with pytest.raises(ArtistCacheStale):
        load_cached_artist("Linkin Park", now=NOW, get=get)
    assert get.call_count == 1


def test_ttl_can_be_changed_without_infrastructure_changes(monkeypatch):
    _, index, processed = _documents(NOW - timedelta(seconds=61))
    monkeypatch.setenv("SOUNDSCOPE_ARTIST_CACHE_TTL_SECONDS", "60")
    with pytest.raises(ArtistCacheStale):
        load_cached_artist(
            "Linkin Park", now=NOW, get=_cache_get(index, processed))


@pytest.mark.parametrize("bad_index", [b"not-json", {}, {"version": 2}])
def test_invalid_index_falls_back_as_cache_error(bad_index):
    if isinstance(bad_index, bytes):
        def get(_key):
            raise S3StorageError("invalid JSON")
    else:
        get = lambda _key: bad_index
    with pytest.raises(ArtistCacheError):
        load_cached_artist("Linkin Park", now=NOW, get=get)


def test_missing_or_invalid_processed_is_cache_error():
    _, index, _ = _documents()
    for processed in (S3ObjectNotFoundError("missing"), {"name": "incomplete"}):
        def get(key, value=processed):
            if key.startswith("cache/"):
                return index
            if isinstance(value, Exception):
                raise value
            return value
        with pytest.raises(ArtistCacheError):
            load_cached_artist("Linkin Park", now=NOW, get=get)


def test_s3_get_json_rejects_invalid_json_and_distinguishes_missing():
    invalid = Mock(get_object=Mock(return_value={"Body": io.BytesIO(b"{")}))
    missing = Mock(get_object=Mock(side_effect=ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")))
    with patch.dict(os.environ, {"SOUNDSCOPE_S3_BUCKET": "private-bucket"}):
        with pytest.raises(S3StorageError, match="JSON válido"):
            get_json("cache/key.json", s3_client=invalid)
        with pytest.raises(S3ObjectNotFoundError):
            get_json("cache/key.json", s3_client=missing)


def test_first_request_misses_then_second_hits_without_pipeline_or_external_work(caplog):
    caplog.set_level(logging.INFO)
    state = {}
    pipeline = Mock(return_value=_result())

    def load(_name):
        if "result" not in state:
            raise ArtistCacheMiss()
        return state["result"], 1.0

    def save(_name, result):
        state["result"] = result

    with patch.object(handler, "load_cached_artist", side_effect=load), \
            patch.object(handler, "save_artist_cache_index", side_effect=save), \
            patch.object(handler, "process_enriched_artist", pipeline), \
            patch("requests.sessions.Session.request") as external_http:
        first = handler.lambda_handler(
            {"pathParameters": {"artist_name": "Linkin Park"}},
            SimpleNamespace(aws_request_id="first"))
        second = handler.lambda_handler(
            {"pathParameters": {"artist_name": " LINKIN   PARK "}},
            SimpleNamespace(aws_request_id="second"))

    assert pipeline.call_count == 1
    external_http.assert_not_called()
    assert json.loads(first["body"]) == json.loads(second["body"])
    records = _records(caplog)[-2:]
    assert records[0]["cache"]["status"] == "miss"
    assert records[0]["metrics"]["cache.misses"] == 1
    assert records[1]["cache"]["status"] == "hit"
    assert records[1]["metrics"]["cache.hits"] == 1
    assert records[1]["metrics"]["cache.age_seconds"] == 1.0
    for absent in ("musicbrainz.requests", "theaudiodb.requests",
                   "s3.raw_writes", "s3.processed_writes", "dynamodb_writes"):
        assert absent not in records[1]["metrics"]


def test_hit_bypasses_pipeline_and_all_writes():
    with patch.object(handler, "load_cached_artist", return_value=(_result(), 2)), \
            patch.object(handler, "process_enriched_artist") as pipeline, \
            patch.object(handler, "save_artist_cache_index") as cache_write, \
            patch("src.pipeline.processing.enriched.save_raw_json") as raw_write, \
            patch("src.pipeline.processing.enriched.save_processed_json") as processed_write, \
            patch("src.pipeline.processing.enriched.save_enriched_artist") as dynamodb_write:
        response = handler.lambda_handler(
            {"pathParameters": {"artist_name": "Linkin Park"}}, None)
    assert response["statusCode"] == 200
    pipeline.assert_not_called()
    cache_write.assert_not_called()
    raw_write.assert_not_called()
    processed_write.assert_not_called()
    dynamodb_write.assert_not_called()


@pytest.mark.parametrize(
    ("failure", "metric", "reason"),
    [(ArtistCacheMiss(), "cache.misses", "not_found"),
     (ArtistCacheStale(), "cache.stale", "stale"),
     (S3StorageError("read failed"), "cache.errors", "error")],
)
def test_cache_fallback_runs_pipeline_and_emits_safe_telemetry(
        failure, metric, reason, caplog):
    caplog.set_level(logging.INFO)
    secret = "secret-must-not-be-logged"
    with patch.object(handler, "load_cached_artist", side_effect=failure), \
            patch.object(handler, "process_enriched_artist", return_value=_result()) as pipeline, \
            patch.object(handler, "save_artist_cache_index"):
        response = handler.lambda_handler(
            {"pathParameters": {"artist_name": "Linkin Park"}}, None)
    assert response["statusCode"] == 200
    pipeline.assert_called_once()
    record = _records(caplog)[-1]
    assert record["cache"] == {"status": "miss", "reason": reason}
    assert record["metrics"][metric] == 1
    assert secret not in caplog.text
    assert "Biography" not in caplog.text


def test_index_is_published_only_after_successful_pipeline_return():
    order = []
    with patch.object(handler, "load_cached_artist", side_effect=ArtistCacheMiss()), \
            patch.object(handler, "process_enriched_artist",
                         side_effect=lambda _name: order.append("pipeline") or _result()), \
            patch.object(handler, "save_artist_cache_index",
                         side_effect=lambda *_args: order.append("index")):
        response = handler.lambda_handler(
            {"pathParameters": {"artist_name": "Linkin Park"}}, None)
    assert response["statusCode"] == 200
    assert order == ["pipeline", "index"]

    with patch.object(handler, "load_cached_artist", side_effect=ArtistCacheMiss()), \
            patch.object(handler, "process_enriched_artist",
                         side_effect=RuntimeError("pipeline failed")), \
            patch.object(handler, "save_artist_cache_index") as cache_write:
        response = handler.lambda_handler(
            {"pathParameters": {"artist_name": "Linkin Park"}}, None)
    assert response["statusCode"] == 500
    cache_write.assert_not_called()


def test_index_write_failure_does_not_change_success_response(caplog):
    caplog.set_level(logging.INFO)
    with patch.object(handler, "load_cached_artist", side_effect=ArtistCacheMiss()), \
            patch.object(handler, "process_enriched_artist", return_value=_result()), \
            patch.object(handler, "save_artist_cache_index",
                         side_effect=S3StorageError("credentials-secret")):
        response = handler.lambda_handler(
            {"pathParameters": {"artist_name": "Linkin Park"}}, None)
    assert response["statusCode"] == 200
    record = _records(caplog)[-1]
    assert record["metrics"]["cache.errors"] == 1
    assert record["cache"]["index_update"] == "error"
    assert "credentials-secret" not in caplog.text
